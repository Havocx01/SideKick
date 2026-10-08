"""Assistant boundary tests use recorded evidence and mocked cloud calls only."""
import asyncio
import io
import json
import time
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_assistant import router
from app.assistant.service import AssistantService
from app.assistant.schemas import AnalysisRecord, AnalysisRequest
from app.assistant.store import AssistantStore
from app.evidence.bundle import load_bundle
from app.config import get_settings


@pytest.fixture
def assistant_app(local_settings):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="test", assistant_presenter_code="",
        assistant_timeout_seconds=0.02,
        assistant_tasks=("investigate", "compare", "warning", "brief"))
    app = FastAPI()
    app.state.assistant = AssistantService(settings)
    app.include_router(router)
    return app


def payload():
    return {"task": "investigate", "candidates": ["logistic_regression/lr1"]}


def test_reopening_and_switching_to_a_brief_reuses_saved_evidence(assistant_app):
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        original = client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
        reopened = client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
        assert reopened["id"] == original["id"] and reopened["reused"]
        brief = client.post("/api/assistant/analyses?reuse=true", json={**payload(), "task": "brief"}, headers=headers).json()
        assert brief["id"] == original["id"] and brief["context"]["task"] == "brief"
        assert brief["result"]["assessment"] == original["result"]["assessment"]
        assert brief["result"]["brief_draft"].startswith("Engineer review draft")
        path = f"/api/assistant/analyses/{brief['id']}/brief"
        assert client.post(path, headers=headers, json={"text": "Unfinished engineer notes", "draft_only": True}).status_code == 200
        restored = client.post("/api/assistant/analyses?reuse=true", json={**payload(), "task": "brief"}, headers=headers).json()
        assert restored["brief_text"] == "Unfinished engineer notes" and restored["brief_saved_at"] is None
        assert client.post(path, headers=headers, json={"text": "Approved draft for export"}).status_code == 200
        assert client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()["brief_saved_at"]
        store = assistant_app.state.assistant.store
        assistant_app.state.assistant.store = AssistantStore(store.path.parent)
        assert client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()["id"] == original["id"]
        forced = client.post("/api/assistant/analyses", json=payload(), headers=headers).json()
        assert forced["id"] != original["id"] and not forced["reused"]
        assert client.post("/api/assistant/analyses?reuse=true", json={**payload(), "candidates": ["logistic_regression/lr2"]}, headers=headers).json()["id"] != forced["id"]
        with TestClient(assistant_app) as stranger:
            isolated = stranger.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
            assert isolated["id"] != forced["id"] and not isolated["reused"]


def test_reuse_shares_live_ai_in_both_directions_without_another_provider_call(assistant_app, monkeypatch):
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = "not-a-real-key"
    calls = []

    async def enhance(result, context, settings, **kwargs):
        calls.append(context.task)
        return result.model_copy(update={"mode": "ai", "interpretation": "Inspect the weakest recorded case."})

    monkeypatch.setattr(provider, "enhance_analysis", enhance)
    loaded = load_bundle(get_settings().bundle_path)

    async def check():
        for first_task, second_task in [("investigate", "brief"), ("brief", "investigate")]:
            owner = first_task
            original = await service.create(loaded, AnalysisRequest(**{**payload(), "task": first_task}), owner, False)
            await asyncio.gather(*service.tasks.values())
            reopened = await service.create(loaded, AnalysisRequest(**{**payload(), "task": second_task}), owner, False, reuse=True)
            assert reopened.id == original.id and reopened.reused and reopened.result.mode == "ai"
            assert reopened.context.task == second_task and not service.tasks
            assert reopened.result.interpretation == "Inspect the weakest recorded case."
            changed = loaded.model_copy(update={"source_digest": "changed-source"})
            fresh = await service.create(changed, original.context, owner, False, reuse=True)
            assert fresh.id != original.id and not fresh.reused
            await asyncio.gather(*service.tasks.values())
    asyncio.run(check())
    assert len(calls) == 4


def test_reuse_skips_expired_public_results_and_unavailable_cloud_access(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        first = client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
        record = service.store.get(first["id"], "owner")
        record.result.mode = "ai"
        service.store.save(record, "owner")
        # Access has been disabled; the old cloud text must not return from the cache.
        off = client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
        assert off["id"] != first["id"] and off["result"]["mode"] == "evidence"
        service.settings.mode = "demo"
        record = service.store.get(off["id"], "owner")
        record.created_at = time.time() - 86401
        service.store.save(record, "owner")
        with service.store.connect() as db:
            db.execute("UPDATE analyses SET public=1 WHERE owner=?", ("owner",))
        fresh = client.post("/api/assistant/analyses?reuse=true", json=payload(), headers=headers).json()
        assert fresh["id"] != off["id"] and not fresh["reused"]
        holdout = client.post("/api/assistant/analyses?reuse=true", json={**payload(), "partition": "holdout"}, headers=headers)
        assert holdout.status_code == 422  # No automatic holdout scoring or development-result substitution.


def test_api_owner_guard_scope_and_safe_export(assistant_app):
    with TestClient(assistant_app) as client:
        assert client.post("/api/assistant/analyses", json=payload()).status_code == 403
        assert client.post("/api/assistant/analyses", json=payload(), headers={"X-Sidekick-Request": "1", "Origin": "https://evil.test"}).status_code == 403
        headers = {"X-Sidekick-Request": "1"}
        bad = client.post("/api/assistant/analyses", json={**payload(), "candidates": ["bad/nope"]}, headers=headers)
        assert bad.status_code == 422
        created = client.post("/api/assistant/analyses", json=payload(), headers=headers)
        assert created.status_code == 200, created.text
        record = created.json()
        assert record["status"] == "completed"
        assert record["result"]["mode"] == "evidence"
        path = "/api/assistant/analyses/" + record["id"]
        assert client.get(path).status_code == 200
        brief = client.post(path + "/brief", json={"text": "<script>alert(1)</script>"}, headers=headers)
        assert brief.status_code == 200
        archive = client.get(path + "/export")
        assert ".zip" in archive.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            assert set(zipped.namelist()) == {"review-brief.html", "analysis.json"}
            document = zipped.read("review-brief.html").decode()
            assert "<script>" not in document
            assert "Engineer review draft" in document and record["id"] in document
            assert record["result"]["evidence_digest"] in document and "Limitations" in document and "Proposed next checks" in document
            exported = json.loads(zipped.read("analysis.json"))
            assert exported["kind"] == "engineer_review_draft" and exported["analysis"]["context"]["candidates"] == payload()["candidates"]
        with TestClient(assistant_app) as stranger:
            assert stranger.get(path).status_code == 404
            assert stranger.get(path + "/export").status_code == 404


def test_disabled_workflows_are_hidden_and_rejected(assistant_app):
    assistant_app.state.assistant.settings.assistant_tasks = ("investigate",)
    with TestClient(assistant_app) as client:
        assert client.get("/api/assistant/capabilities").json()["tasks"] == ["investigate"]
        brief = client.post("/api/assistant/analyses", json={**payload(), "task": "brief"}, headers={"X-Sidekick-Request": "1"})
        assert brief.status_code == 403


def seed_public_records(store, record, owner):
    with store.connect() as db:
        copies = [record.model_copy(update={"id": str(uuid4())}) for _ in range(300)]
        db.executemany("INSERT INTO analyses(id,owner,payload,public) VALUES(?,?,?,1)",
            [(copy.id, owner, copy.model_dump_json()) for copy in copies])


def test_public_analysis_has_no_request_allowance(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    monkeypatch.setattr(service.settings, "mode", "demo")
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    with TestClient(assistant_app) as client:
        headers = {"X-Sidekick-Request": "1"}
        first = client.post("/api/assistant/analyses", json=payload(), headers=headers).json()
        seed_public_records(service.store, AnalysisRecord.model_validate(first), "owner")
        response = client.post("/api/assistant/analyses", json=payload(), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_records_from_an_older_contract_are_upgraded_on_startup(assistant_app):
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        record = client.post("/api/assistant/analyses", json=payload(), headers=headers).json()
        path = "/api/assistant/analyses/" + record["id"]
        assert client.post(path + "/brief", json={"text": "Saved review"}, headers=headers).status_code == 200
        store = assistant_app.state.assistant.store
        with store.connect() as db:
            saved = json.loads(db.execute("SELECT payload FROM analyses WHERE id=?", (record["id"],)).fetchone()[0])
            for source in saved["result"]["sources"]:
                del source["display"], source["context"]
            db.execute("UPDATE analyses SET payload=? WHERE id=?", (json.dumps(saved), record["id"]))
            db.execute("INSERT INTO analyses(id,owner,payload) VALUES('broken','x','not json')")
        assistant_app.state.assistant.store = AssistantStore(store.path.parent)
        reopened = client.get(path)
        assert reopened.status_code == 200
        assert reopened.json()["result"]["sources"][0]["display"]
        assert reopened.json()["brief_text"] == "Saved review"
        with store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM analyses WHERE id='broken'").fetchone()[0] == 0


def test_access_attempts_remain_throttled(tmp_path):
    store = AssistantStore(tmp_path)
    for _ in range(5):
        store.attempt("host")
    with pytest.raises(ValueError):
        store.attempt("host")


def test_rejected_ai_output_falls_back_to_recorded_evidence(assistant_app, monkeypatch):
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "test-not-a-real-key"
    async def invalid(result, context, settings, **kwargs):
        raise ValueError("Cloud interpretation contained an unsupported numeric claim.")
    monkeypatch.setattr(provider, "enhance_analysis", invalid)
    loaded = load_bundle(get_settings().bundle_path)

    async def run():
        record = await assistant.create(loaded, AnalysisRequest(**payload()), "owner", False)
        await asyncio.gather(*assistant.tasks.values())
        done = assistant.store.get(record.id, "owner")
        assert done.status == "completed" and done.result.mode == "evidence"
        assert done.result.interpretation is None and "failed verification" in done.result.fallback_reason
    asyncio.run(run())


@pytest.mark.parametrize("status,code,expected", [
    (401, "invalid_api_key", "Replace OPENAI_API_KEY"),
    (403, "permission_denied", "model permissions"),
    (429, "insufficient_quota", "API billing"),
    (429, "rate_limit_exceeded", "Wait a moment"),
    (404, "model_not_found", "SIDEKICK_ASSISTANT_MODEL"),
    (500, "server_error", "Try again later"),
])
def test_provider_errors_are_actionable_without_leaking_responses(assistant_app, monkeypatch, status, code, expected):
    import httpx
    from openai import APIStatusError, AuthenticationError, PermissionDeniedError, RateLimitError
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "not-a-real-key"
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    kind = {401: AuthenticationError, 403: PermissionDeniedError, 429: RateLimitError}.get(status, APIStatusError)
    async def fail(*args, **kwargs):
        raise kind("Sensitive provider response with sk-secret", response=response, body={"code": code})
    monkeypatch.setattr(provider, "enhance_analysis", fail)
    loaded = load_bundle(get_settings().bundle_path)

    async def run():
        record = await assistant.create(loaded, AnalysisRequest(**payload()), "owner", False)
        await asyncio.gather(*assistant.tasks.values())
        done = assistant.store.get(record.id, "owner")
        assert done.status == "completed" and done.result.mode == "evidence"
        assert expected in done.result.fallback_reason
        assert "sk-secret" not in done.model_dump_json()
        assert done.result.assessment and done.result.sources
    asyncio.run(run())


def test_timeout_cancel_consent_and_restart(assistant_app, monkeypatch):
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "test-not-a-real-key"
    calls = []
    async def slow(result, context, settings, **kwargs):
        calls.append(context)
        await asyncio.sleep(10)
        return result
    monkeypatch.setattr(provider, "enhance_analysis", slow)
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())

    async def run():
        record = await assistant.create(loaded, context, "owner", False)
        await asyncio.wait_for(asyncio.gather(*assistant.tasks.values()), timeout=1)
        done = assistant.store.get(record.id, "owner")
        assert done.status == "completed"
        assert "timed out" in done.result.fallback_reason
        record = await assistant.create(loaded, context, "owner", False)
        await asyncio.sleep(0)
        cancelled = await assistant.cancel(record.id, "owner")
        assert cancelled.status == "cancelled"
        record = await assistant.create(loaded, context, "owner", True)
        assert record.status == "completed"
        assert "off" in record.result.fallback_reason
        assistant.store.set_consent("owner", "uploaded", True)
        upload_context = context.model_copy(update={"experiment_id": "uploaded"})
        record = await assistant.create(loaded.model_copy(update={"experiment_id": "uploaded"}), upload_context, "owner", True)
        await asyncio.sleep(0)
        await assistant.revoke("owner", "uploaded")
        assert assistant.store.get(record.id, "owner").status == "cancelled"
        record.status = "running"
        assistant.store.save(record, "owner")
        restarted = AssistantStore(assistant.settings.artifacts_dir / "assistant")
        assert restarted.get(record.id, "owner").status == "interrupted"
        await assistant.close()
    asyncio.run(run())
    assert len(calls) == 3


def test_demo_unlock_is_browser_bound_and_replay_never_live(assistant_app):
    settings = assistant_app.state.assistant.settings
    settings.mode = "demo"
    settings.assistant_live_enabled = True
    settings.openai_api_key = "not-real"
    settings.assistant_presenter_code = "presenter"
    @assistant_app.middleware("http")
    async def demo_session(request, call_next):
        request.state.demo_token = request.cookies.get("sidekick_demo", "default-test-session")
        return await call_next(request)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        before = client.get("/api/assistant/capabilities").json()
        assert before["unlock_available"] and not before["live_available"]
        assert client.post("/api/assistant/access", headers=headers, json={"code": "bad"}).status_code == 403
        assert client.post("/api/assistant/access", headers=headers, json={"code": "presenter"}).status_code == 200
        assert client.get("/api/assistant/capabilities").json()["live_available"]
        with TestClient(assistant_app) as other:
            other.cookies.set("sidekick_demo", "another-test-session")
            assert not other.get("/api/assistant/capabilities").json()["live_available"]
        settings.mode = "replay"
        assert not client.get("/api/assistant/capabilities").json()["live_available"]


def test_revoked_consent_hides_completed_ai_and_saved_brief(assistant_app, monkeypatch):
    from app.api import routes_assistant
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "not-real"
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        record = client.post("/api/assistant/analyses", headers=headers, json={**payload(), "experiment_id": "uploaded"}).json()
        path = "/api/assistant/analyses/" + record["id"]
        with assistant.store.connect() as db:
            who = db.execute("SELECT owner FROM analyses WHERE id=?", (record["id"],)).fetchone()[0]
        saved = assistant.store.get(record["id"], who)
        saved.result.mode = "ai"
        saved.result.summary = "private cloud interpretation"
        saved.brief_text = "private cloud draft"
        assistant.store.save(saved, who)
        response = client.get(path).json()
        assert response["result"]["mode"] == "evidence"
        assert response["brief_text"] is None
        assert "private cloud" not in client.get(path + "/export").text

def test_revocation_does_not_resurrect_ai_after_reconsent(assistant_app, monkeypatch):
    from app.api import routes_assistant
    assistant = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        record = client.post("/api/assistant/analyses", headers=headers, json={**payload(), "experiment_id": "uploaded"}).json()
        path = "/api/assistant/analyses/" + record["id"]
        with assistant.store.connect() as db:
            who = db.execute("SELECT owner FROM analyses WHERE id=?", (record["id"],)).fetchone()[0]
        saved = assistant.store.get(record["id"], who)
        saved.result.mode = "ai"
        assistant.store.save(saved, who)
        assert client.post("/api/assistant/consent/uploaded", headers=headers, json={"allowed": False}).status_code == 200
        assert client.post("/api/assistant/consent/uploaded", headers=headers, json={"allowed": True}).status_code == 200
        response = client.get(path)
        assert response.json()["result"]["mode"] == "evidence"
        assert response.headers["cache-control"] == "no-store"




def test_investigation_can_become_a_brief_without_a_second_ai_request(assistant_app):
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        original = client.post("/api/assistant/analyses", json=payload(), headers=headers).json()
        review = client.post(f"/api/assistant/analyses/{original['id']}/review", headers=headers)
        assert review.status_code == 200, review.text
        saved = review.json()
        assert saved["context"]["task"] == "brief" and saved["id"] != original["id"]
        assert saved["result"]["evidence_digest"] == original["result"]["evidence_digest"]
        assert saved["result"]["assessment"] == original["result"]["assessment"]
        assert "Assessment" in saved["result"]["brief_draft"]
        assert assistant_app.state.assistant.tasks == {}
        assistant_app.state.assistant.settings.assistant_tasks = ("investigate",)
        assert client.post(f"/api/assistant/analyses/{original['id']}/review", headers=headers).status_code == 403


def test_data_review_api_consent_and_scope(assistant_app, tmp_path):
    from uuid import uuid4
    from app.data.synthetic import make_synthetic_dataset
    from app.experiments.datasets import register
    from app.experiments.store import Workspace
    workspace = Workspace(tmp_path / "workspace")
    assistant_app.state.jobs = SimpleNamespace(workspace=workspace)
    assistant_app.state.assistant.settings.assistant_tasks += ("data",)
    id = str(uuid4())
    path = workspace.directory("datasets", id) / "data.csv"
    path.parent.mkdir(parents=True)
    make_synthetic_dataset().frame.to_csv(path, index=False)
    dataset = register(workspace, path, id, "private.csv")
    before = workspace.get("datasets", id)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        caps = client.get("/api/assistant/capabilities", params={"dataset_id": id}).json()
        assert caps["consent_required"] and not caps["consent_granted"]
        response = client.post("/api/assistant/analyses", json={"task": "data", "dataset_id": id, "mapping": dataset.mapping.model_dump()}, headers=headers)
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["result"]["suggested_mapping"] and record["result"]["assessment"]
        assert client.get(f"/api/assistant/analyses/{record['id']}").status_code == 200
        scope = f"dataset:{id}"
        assert client.post(f"/api/assistant/consent/{scope}", json={"allowed": True}, headers=headers).status_code == 200
        assert client.get("/api/assistant/capabilities", params={"dataset_id": id}).json()["consent_granted"]
        assert client.post(f"/api/assistant/consent/{scope}", json={"allowed": False}, headers=headers).status_code == 200
        assert workspace.get("datasets", id) == before
        assert client.post("/api/assistant/analyses", json={"task": "data", "dataset_id": "../../secret"}, headers=headers).status_code == 404
        assistant_app.state.assistant.settings.mode = "replay"
        assert client.post("/api/assistant/analyses", json={"task": "data", "dataset_id": id}, headers=headers).status_code == 403


def test_public_review_has_no_request_allowance(assistant_app, monkeypatch):
    from app.api import routes_assistant
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        original = client.post("/api/assistant/analyses", json=payload(), headers=headers).json()
        store = assistant_app.state.assistant.store
        with store.connect() as db:
            who = db.execute("SELECT owner FROM analyses WHERE id=?", (original["id"],)).fetchone()[0]
        seed_public_records(store, AnalysisRecord.model_validate(original), who)
        assistant_app.state.assistant.settings.mode = "demo"
        monkeypatch.setattr(routes_assistant, "visitor", lambda *args: who)
        response = client.post(f"/api/assistant/analyses/{original['id']}/review", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["context"]["task"] == "brief"


def test_live_analysis_ignores_legacy_usage_and_has_no_session_or_daily_cap(assistant_app, monkeypatch):
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "not-a-real-key"
    with assistant.store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS usage(owner TEXT NOT NULL, created REAL NOT NULL)")
        db.executemany("INSERT INTO usage VALUES(?,?)", [("owner", time.time())] * 30)
    calls = []
    async def enhance(result, context, settings, **kwargs):
        calls.append(context)
        return result.model_copy(update={"mode": "ai"})
    monkeypatch.setattr(provider, "enhance_analysis", enhance)
    loaded = load_bundle(get_settings().bundle_path)

    async def run():
        for _ in range(27):
            record = await assistant.create(loaded, AnalysisRequest(**payload()), "owner", False)
            assert record.status == "running"
            await asyncio.gather(*assistant.tasks.values())
            done = assistant.store.get(record.id, "owner")
            assert done.status == "completed" and done.result.mode == "ai"
            assert done.result.fallback_reason is None
    asyncio.run(run())
    assert len(calls) == 27
