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


def test_prompt_upgrade_preserves_drafts_only_for_same_owner_and_evidence(assistant_app):
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())

    async def check():
        old = await service.create(loaded, context, "owner", False)
        old.cache_fingerprint = "sidekick-analysis-v2.2:" + old.cache_fingerprint.partition(":")[2]
        old.brief_text = "Engineer-written notes"
        old.brief_saved_at = time.time()
        service.store.save(old, "owner")
        updated = await service.create(loaded, context, "owner", False, reuse=True)
        assert updated.id == old.id and updated.reused  # Version changes alone never start another paid job.
        assert updated.brief_text == old.brief_text and updated.brief_saved_at == old.brief_saved_at
        assert service.store.get(old.id, "owner").brief_text == old.brief_text
        different = await service.create(loaded.model_copy(update={"source_digest": "different"}), context, "owner", False)
        assert different.brief_text is None
        stranger = await service.create(loaded, context, "stranger", False)
        assert stranger.brief_text is None
        updated.brief_text = ""
        updated.updated_at = time.time() + 1
        service.store.save(updated, "owner")
        rerun = await service.create(loaded, context, "owner", False)
        assert rerun.brief_text == ""  # An explicitly cleared draft stays cleared.

    asyncio.run(check())


def test_unedited_generated_brief_is_regenerated_when_analysis_is_rerun(assistant_app):
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**{**payload(), "task": "brief"})

    async def check():
        old = await service.create(loaded, context, "owner", False)
        old.brief_text = old.result.brief_draft
        old.brief_saved_at = time.time()
        service.store.save(old, "owner")
        updated = await service.create(loaded, context, "owner", False)
        assert updated.result.brief_draft
        assert updated.brief_text is None and updated.brief_saved_at is None
        assert service.store.get(old.id, "owner").brief_saved_at

    asyncio.run(check())


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
        # Replay denies cloud output even if the saved result belongs to this owner.
        service.settings.mode = "replay"
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
            assert db.execute("SELECT COUNT(*) FROM analyses WHERE id='broken'").fetchone()[0] == 1


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
        from app.assistant.store import AnalysisRevokedError
        with pytest.raises(AnalysisRevokedError):
            assistant.store.save(record, "owner")
        # Restart recovery uses an independently admitted, non-revoked record.
        record.id = str(uuid4())
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
        assert saved["context"]["task"] == "brief" and saved["id"] == original["id"]
        assert saved["result"]["evidence_digest"] == original["result"]["evidence_digest"]
        assert saved["result"]["assessment"] == original["result"]["assessment"]
        assert "Review focus" in saved["result"]["brief_draft"]
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

def test_model_upgrade_requires_new_output_but_preserves_human_draft(assistant_app, monkeypatch):
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = 'mock-only'
    calls = []
    async def enhance(result, context, settings, **kwargs):
        calls.append(settings.assistant_model)
        return result.model_copy(update={'mode': 'ai', 'model': settings.assistant_model})
    monkeypatch.setattr(provider, 'enhance_analysis', enhance)
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())
    async def check():
        old = await service.create(loaded, context, 'owner', False)
        await asyncio.gather(*service.tasks.values())
        old = service.store.get(old.id, 'owner')
        old.brief_text = 'Human review retained'
        service.store.save(old, 'owner')
        service.settings.assistant_model = 'new-model'
        reused = await service.create(loaded, context, 'owner', False, reuse=True)
        assert reused.id == old.id and reused.result.model == 'test'
        new = await service.create(loaded, context, 'owner', False, reuse=False)
        assert new.id != old.id and new.brief_text == old.brief_text
        assert new.draft_fingerprint == old.draft_fingerprint
        await asyncio.gather(*service.tasks.values())
        again = await service.create(loaded, context.model_copy(update={'task': 'brief'}), 'owner', False, reuse=True)
        assert again.id == new.id
    asyncio.run(check())
    assert calls == ['test', 'new-model']


def test_public_capacity_is_atomic_and_existing_records_remain_writable(assistant_app):
    from concurrent.futures import ThreadPoolExecutor
    from app.assistant.store import AnalysisCapacityError
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path)
    original = asyncio.run(service.create(loaded, AnalysisRequest(**payload()), 'local', False))
    service.store.max_public_records = 2
    service.store.max_public_bytes = 1024 * 1024
    def admit(index):
        record = original.model_copy(update={'id': str(uuid4())}, deep=True)
        try:
            service.store.save(record, f'visitor-{index}', public=True)
            return record.id, f'visitor-{index}'
        except AnalysisCapacityError:
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        admitted = [item for item in pool.map(admit, range(6)) if item]
    assert len(admitted) == 1  # The existing legacy/local row also consumes shared capacity.
    for id, owner in admitted:
        record = service.store.get(id, owner)
        record.brief_text = '\x00' * 12000
        service.store.save(record, owner)
        assert service.store.get(id, owner).brief_text == record.brief_text
    service.store.save(original.model_copy(update={'id': str(uuid4())}), 'local')
    with service.store.connect() as db:
        db.execute("UPDATE analyses SET payload=json_set(payload,'$.created_at',?) WHERE id=?", (time.time()-86401, admitted[0][0]))
    assert admit(8) is None  # Expiry frees one slot, which the retained local copy occupies.


def test_demo_capacity_rejects_before_provider_work(assistant_app, monkeypatch):
    from app.api import routes_assistant
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.mode = 'demo'
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = 'mock-only'
    service.store.max_public_records = 1
    service.store.unlock('owner')
    monkeypatch.setattr(routes_assistant, 'visitor', lambda *args: 'owner')
    calls = []
    async def enhance(result, *args, **kwargs):
        calls.append(1)
        return result
    monkeypatch.setattr(provider, 'enhance_analysis', enhance)
    with TestClient(assistant_app) as client:
        headers = {'X-Sidekick-Request': '1'}
        first = client.post('/api/assistant/analyses', json=payload(), headers=headers)
        assert first.status_code == 200
        second = client.post('/api/assistant/analyses', json=payload(), headers=headers)
        assert second.status_code == 503
        assert 'capacity' in second.json()['detail']
    assert len(calls) <= 1

def test_prompt_contract_and_verified_legacy_draft_survive_restart(assistant_app, monkeypatch):
    from app.assistant import investigation
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())
    async def check():
        old = await service.create(loaded, context, 'owner', False)
        old.draft_fingerprint = None
        old.cache_fingerprint = 'sidekick-analysis-v2.2:' + service.identities(loaded, context, False)[2]
        old.brief_text = 'Legacy human notes'
        service.store.save(old, 'owner')
        with service.store.connect() as db:
            data = json.loads(db.execute('SELECT payload FROM analyses WHERE id=?', (old.id,)).fetchone()[0])
            for source in data['result']['sources']:
                del source['display'], source['context']
            db.execute('UPDATE analyses SET payload=? WHERE id=?', (json.dumps(data), old.id))
        service.store = AssistantStore(service.store.path.parent)
        monkeypatch.setattr(investigation, 'PROMPT_VERSION', 'sidekick-investigation-v5-test')
        upgraded = await service.create(loaded, context, 'owner', False, reuse=True)
        assert upgraded.id != old.id and upgraded.brief_text == 'Legacy human notes'
        assert upgraded.result.prompt_version == 'sidekick-investigation-v5-test'
        assert service.store.get(old.id, 'owner').brief_text == 'Legacy human notes'
    asyncio.run(check())


def test_legacy_over_capacity_is_readable_but_new_admission_is_blocked(assistant_app):
    from app.assistant.store import AnalysisCapacityError
    service = assistant_app.state.assistant
    original = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), 'owner', False))
    with service.store.connect() as db:
        db.execute('UPDATE analyses SET public=1,reserved_bytes=0 WHERE id=?', (original.id,))
    service.store.max_public_bytes = 1
    assert service.store.get(original.id, 'owner').id == original.id
    original.brief_text = 'Saved at capacity'
    service.store.save(original, 'owner')
    with pytest.raises(AnalysisCapacityError):
        service.store.save(original.model_copy(update={'id': str(uuid4())}), 'owner', public=True)
    assert service.store.get(original.id, 'owner').brief_text == 'Saved at capacity'

def test_demo_result_growth_is_bounded_and_full_draft_reservation_survives(assistant_app, monkeypatch):
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.mode = 'demo'
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = 'mock-only'
    service.store.unlock('owner')
    service.store.max_public_records = 1
    async def oversized(result, *args, **kwargs):
        return result.model_copy(update={'summary': '😀' * 20000, 'mode': 'ai'})
    monkeypatch.setattr(provider, 'enhance_analysis', oversized)
    async def check():
        record = await service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), 'owner', False)
        await asyncio.gather(*service.tasks.values())
        done = service.store.get(record.id, 'owner')
        assert done.status == 'completed' and done.result.mode == 'evidence'
        assert 'failed verification' in done.result.fallback_reason
        done.brief_text = '\x00' * 12000
        service.store.save(done, 'owner')
        assert service.store.get(done.id, 'owner').brief_text == done.brief_text
    asyncio.run(check())


def test_public_payload_budget_rejects_atomically_without_deleting_current_data(assistant_app):
    from app.assistant.store import AnalysisCapacityError
    service = assistant_app.state.assistant
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), 'owner', False))
    service.store.max_public_bytes = 1
    with pytest.raises(AnalysisCapacityError):
        service.store.save(record.model_copy(update={'id': str(uuid4())}), 'visitor', public=True)
    assert service.store.get(record.id, 'owner').id == record.id
    with service.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM analyses').fetchone()[0] == 1


@pytest.mark.parametrize("origin,retained", [("cloud", False), ("unknown", False), ("evidence", True)])
def test_legacy_provenance_survives_migration_revocation_and_reuse(assistant_app, monkeypatch, origin, retained):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    context = AnalysisRequest(**payload(), experiment_id="uploaded")
    record = asyncio.run(service.create(loaded, context, "owner", True))
    record.brief_text = "Original legacy notes"
    record.brief_saved_at = time.time()
    data = record.model_dump(mode="json")
    if origin == "unknown":
        data["result"] = None
    else:
        data["result"]["mode"] = "ai" if origin == "cloud" else "evidence"
        for source in data["result"]["sources"]:
            del source["display"], source["context"]
    with service.store.connect() as db:
        db.execute("UPDATE analyses SET payload=? WHERE id=?", (json.dumps(data), record.id))
        db.execute("DELETE FROM analysis_provenance WHERE id=?", (record.id,))
    # Running a migration twice cannot erase the original cloud/unknown classification.
    service.store = AssistantStore(service.store.path.parent)
    service.store = AssistantStore(service.store.path.parent)
    assert service.store.provenance(record.id, "owner") == (origin, origin)
    headers = {"X-Sidekick-Request": "1"}
    path = f"/api/assistant/analyses/{record.id}"
    with TestClient(assistant_app) as client:
        assert client.post("/api/assistant/consent/uploaded", headers=headers, json={"allowed": False}).status_code == 200
        saved = service.store.get(record.id, "owner")
        assert (saved.brief_text == "Original legacy notes") is retained
        assert client.post("/api/assistant/consent/uploaded", headers=headers, json={"allowed": True}).status_code == 200
        restored = client.get(path).json()
        assert (restored["brief_text"] == "Original legacy notes") is retained
        assert restored["result"]["mode"] == "evidence"
        copied = client.post("/api/assistant/analyses", headers=headers, json=context.model_dump(mode="json")).json()
        assert (copied["brief_text"] == "Original legacy notes") is retained
        review = client.post(path + "/review", headers=headers)
        if retained:
            assert review.status_code == 200 and review.json()["brief_text"] == "Original legacy notes"
            with zipfile.ZipFile(io.BytesIO(client.get(path + "/export").content)) as archive:
                assert "Original legacy notes" in archive.read("review-brief.html").decode()
        else:
            assert review.status_code == 403
            assert client.get(path + "/export").status_code == 403
            # Even after reconsent, a delayed autosave from the old inspector cannot resurrect this text.
            stale = client.post(path + "/brief", headers=headers, json={"text": "Original legacy notes", "draft_only": True})
            assert stale.status_code == 403
            assert service.store.get(record.id, "owner").brief_text is None


def test_editing_and_copying_cloud_briefs_retains_their_origin(assistant_app):
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    context = AnalysisRequest(**payload(), experiment_id="uploaded")
    record = asyncio.run(service.create(loaded, context, "owner", True))
    record.result.mode = "ai"
    service.store.save(record, "owner")
    record.brief_text = "Cloud-derived draft"
    service.store.save(record, "owner")
    assert service.store.provenance(record.id, "owner") == ("cloud", "cloud")
    record.result.mode = "evidence"
    record.brief_text = "Edited cloud-derived draft"
    service.store.save(record, "owner")
    assert service.store.provenance(record.id, "owner") == ("evidence", "cloud")
    asyncio.run(service.revoke("owner", "uploaded"))
    assert service.store.get(record.id, "owner").brief_text is None


def test_active_reuse_coalesces_brief_equivalent_and_preserves_owner(assistant_app, monkeypatch):
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = "mock-only"
    service.settings.assistant_timeout_seconds = 2
    calls = []
    async def check():
        gate = asyncio.Event()
        async def enhance(result, *args, **kwargs):
            calls.append(1)
            await gate.wait()
            return result.model_copy(update={"mode": "ai"})
        monkeypatch.setattr(provider, "enhance_analysis", enhance)
        loaded = load_bundle(get_settings().bundle_path)
        context = AnalysisRequest(**payload())
        first = await service.create(loaded, context, "owner", False, reuse=True)
        await asyncio.sleep(0)
        same = await service.create(loaded, context, "owner", False, reuse=True)
        brief = await service.create(loaded, context.model_copy(update={"task": "brief"}), "owner", False, reuse=True)
        assert same.id == brief.id == first.id and same.status == brief.status == "running"
        other = await service.create(loaded, context, "other", False, reuse=True)
        assert other.id != first.id and other.result.mode == "evidence"
        gate.set()
        await asyncio.gather(*service.tasks.values())
    asyncio.run(check())
    assert len(calls) == 1


def test_get_currency_is_response_only_and_never_regenerates_historical_output(assistant_app, monkeypatch):
    from app.api import routes_assistant
    from app.assistant import provider
    service = assistant_app.state.assistant
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = "mock-only"
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    calls = []
    async def enhance(result, *args, **kwargs):
        calls.append(1)
        return result.model_copy(update={"mode": "ai", "model": service.settings.assistant_model})
    monkeypatch.setattr(provider, "enhance_analysis", enhance)
    async def make():
        record = await service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), "owner", False)
        await asyncio.gather(*service.tasks.values())
        return record.id
    id = asyncio.run(make())
    path = f"/api/assistant/analyses/{id}"
    with TestClient(assistant_app) as client:
        assert client.get(path).json()["output_currency"] == "current"
        service.settings.assistant_model = "changed-model"
        historical = client.get(path).json()
        assert historical["output_currency"] == "historical" and historical["result"]["model"] == "test"
        service.settings.assistant_live_enabled = False
        service.settings.openai_api_key = ""
        assert client.get(path).json()["result"]["mode"] == "ai"  # Configuration availability is not consent revocation.
        reused = client.post("/api/assistant/analyses?reuse=true", headers={"X-Sidekick-Request": "1"}, json=payload()).json()
        assert reused["id"] == id and reused["result"]["model"] == "test"
        with service.store.connect() as db:
            stored = json.loads(db.execute("SELECT payload FROM analyses WHERE id=?", (id,)).fetchone()[0])
            assert "output_currency" not in stored
    assert len(calls) == 1


def test_replay_capacity_expiry_preserves_legacy_local_records(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    original = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), "owner", False))
    original.created_at = time.time() - 86401
    original.brief_text = "Retained local draft"
    service.store.save(original, "owner")
    service.settings.mode = "replay"
    service.store.max_public_records = 2
    service.store.max_public_bytes = 1024 * 1024
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        assert client.get(f"/api/assistant/analyses/{original.id}").status_code == 200
        first = client.post("/api/assistant/analyses", headers=headers, json=payload()).json()
        assert first["result"]["mode"] == "evidence"
        assert client.post("/api/assistant/analyses", headers=headers, json=payload()).status_code == 503
        first_record = service.store.get(first["id"], "owner")
        first_record.created_at = time.time() - 86401
        service.store.save(first_record, "owner")
        assert client.get(f"/api/assistant/analyses/{first['id']}").status_code == 404
        assert client.get(f"/api/assistant/analyses/{first['id']}/export").status_code == 404
        assert client.post("/api/assistant/analyses", headers=headers, json=payload()).status_code == 200
        assert service.store.get(original.id, "owner").brief_text == "Retained local draft"
    # Changing mode never makes local/legacy payload bytes disappear from the public budget.
    service.store.max_public_bytes = 1
    with TestClient(assistant_app) as client:
        assert client.post("/api/assistant/analyses", headers=headers, json=payload()).status_code == 503
        saved = service.store.get(original.id, "owner")
        saved.brief_text = "Still editable at capacity"
        service.store.save(saved, "owner")


def test_fresh_provider_fallback_is_current_and_retry_does_not_reuse_active_work(assistant_app, monkeypatch):
    from app.api import routes_assistant
    from app.assistant import provider, investigation
    service = assistant_app.state.assistant
    service.settings.assistant_live_enabled = True
    service.settings.openai_api_key = "mock-only"
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    calls = []
    async def unavailable(*args, **kwargs):
        calls.append(1)
        raise ValueError("Mock verification failure")
    monkeypatch.setattr(provider, "enhance_analysis", unavailable)
    async def make():
        loaded = load_bundle(get_settings().bundle_path)
        context = AnalysisRequest(**payload())
        record = await service.create(loaded, context, "owner", False)
        await asyncio.gather(*service.tasks.values())
        same = await service.create(loaded, context, "owner", False, reuse=True)
        assert same.id == record.id and same.result.mode == "evidence"
        return record.id
    id = asyncio.run(make())
    with TestClient(assistant_app) as client:
        assert client.get(f"/api/assistant/analyses/{id}").json()["output_currency"] == "current"
        monkeypatch.setattr(investigation, "PROMPT_VERSION", "different-contract")
        assert client.get(f"/api/assistant/analyses/{id}").json()["output_currency"] == "historical"
    assert len(calls) == 1


def test_unreadable_legacy_records_cannot_break_lookup_or_expiry(assistant_app):
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())
    record = asyncio.run(service.create(loaded, context, "owner", False))
    with service.store.connect() as db:
        db.execute("INSERT INTO analyses(id,owner,payload,public) VALUES('broken-json','owner','not json',1)")
        db.execute("INSERT INTO analyses(id,owner,payload) VALUES('broken-contract','owner',?)", (json.dumps({"status": "completed", "result": {}, "cache_fingerprint": record.cache_fingerprint, "draft_fingerprint": record.draft_fingerprint, "created_at": time.time() + 1}),))
    service.store = AssistantStore(service.store.path.parent)
    assert service.store.latest("owner", record.cache_fingerprint).id == record.id
    assert service.store.latest_scoped("owner", record.draft_fingerprint).id == record.id
    service.store.expire_public()
    with pytest.raises(KeyError):
        service.store.get("broken-contract", "owner")
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 3


def test_retired_model_configuration_remains_readable_as_historical(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), "owner", False))
    original = record.result.model_dump(mode="json")
    record.context.candidates = ["retired/old-configuration"]
    service.store.save(record, "owner")
    with TestClient(assistant_app) as client:
        response = client.get(f"/api/assistant/analyses/{record.id}")
        assert response.status_code == 200
        assert response.json()["output_currency"] == "historical"
        assert response.json()["result"] == original


def test_presenter_expiry_hides_cloud_and_denies_draft_writes_and_export(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), "owner", False))
    record.result.mode = "ai"
    record.result.summary = "Private presenter cloud interpretation"
    record.brief_text = "Private presenter cloud brief"
    service.store.save(record, "owner")
    service.settings.mode = "demo"
    service.store.unlock("owner")
    with service.store.connect() as db:
        db.execute("UPDATE sessions SET unlocked_until=? WHERE owner='owner'", (time.time() - 1,))
    path = f"/api/assistant/analyses/{record.id}"
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        response = client.get(path)
        assert "Private presenter cloud" not in response.text
        assert response.json()["brief_text"] is None
        assert client.post(path + "/brief", headers=headers, json={"text": "Late cloud autosave", "draft_only": True}).status_code == 403
        assert client.post(path + "/review", headers=headers).status_code == 403
        assert client.get(path + "/export").status_code == 403


def test_revocation_racing_with_an_admitted_draft_save_is_rejected_atomically(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    context = AnalysisRequest(**payload(), experiment_id="uploaded")
    record = asyncio.run(service.create(loaded, context, "owner", True))
    record.result.mode = "ai"
    record.brief_text = "Cloud text before revocation"
    service.store.save(record, "owner")
    service.store.set_consent("owner", "uploaded", True)
    original_save = service.store.save
    def race(record, owner, *args, **kwargs):
        service.store.set_consent(owner, "uploaded", False)
        service.store.revoke_results(owner, "uploaded")
        return original_save(record, owner, *args, **kwargs)
    monkeypatch.setattr(service.store, "save", race)
    path = f"/api/assistant/analyses/{record.id}"
    with TestClient(assistant_app) as client:
        response = client.post(path + "/brief", headers={"X-Sidekick-Request": "1"}, json={"text": "Stale cloud autosave", "draft_only": True})
        assert response.status_code == 403
        assert service.store.get(record.id, "owner").brief_text is None
        service.store.set_consent("owner", "uploaded", True)
        assert "Stale cloud autosave" not in client.get(path).text


def test_revoke_persists_privacy_before_cancellation_or_restart(assistant_app, monkeypatch):
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    context = AnalysisRequest(**payload(), experiment_id="uploaded")
    record = asyncio.run(service.create(loaded, context, "owner", True))
    record.result.mode = "ai"
    record.brief_text = "Cloud draft before simulated interruption"
    service.store.save(record, "owner")
    service.store.set_consent("owner", "uploaded", True)
    service.contexts[record.id] = ("owner", "uploaded", True)
    async def interrupted_cancel(id, owner):
        assert not service.store.consent(owner, "uploaded")
        assert service.store.get(id, owner).brief_text is None
        assert service.store.revoked(id, owner)
        raise RuntimeError("Simulated process interruption before cancellation finishes")
    monkeypatch.setattr(service, "cancel", interrupted_cancel)
    with pytest.raises(RuntimeError):
        asyncio.run(service.revoke("owner", "uploaded"))
    restarted = AssistantStore(service.store.path.parent)
    assert not restarted.consent("owner", "uploaded")
    assert restarted.get(record.id, "owner").brief_text is None
    assert restarted.revoked(record.id, "owner")


def test_denied_retired_cloud_model_returns_explanatory_failure(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(loaded, AnalysisRequest(**payload(), experiment_id="uploaded"), "owner", True))
    record.result.mode = "ai"
    record.result.summary = "Private retired cloud interpretation"
    record.context.candidates = ["retired/old-configuration"]
    service.store.save(record, "owner")
    with TestClient(assistant_app) as client:
        response = client.get(f"/api/assistant/analyses/{record.id}")
        assert response.status_code == 403
        assert "historical model" in response.json()["detail"]
        assert "Private retired cloud" not in response.text


def test_review_conversion_preserves_concurrent_saved_draft_and_origin(assistant_app, monkeypatch):
    from app.api import routes_assistant
    from app.assistant import evidence
    service = assistant_app.state.assistant
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path), AnalysisRequest(**payload()), "owner", False))
    record.result.mode = "ai"
    service.store.save(record, "owner")
    original_convert = evidence.with_brief
    saved_at = time.time()
    def concurrent_save(result, context):
        newest = service.store.get(record.id, "owner")
        newest.brief_text = "Newer explicitly saved review"
        newest.brief_saved_at = saved_at
        service.store.save(newest, "owner")
        return original_convert(result, context)
    monkeypatch.setattr(evidence, "with_brief", concurrent_save)
    path = f"/api/assistant/analyses/{record.id}"
    with TestClient(assistant_app) as client:
        response = client.post(path + "/review", headers={"X-Sidekick-Request": "1"})
        assert response.status_code == 200
        assert response.json()["brief_text"] == "Newer explicitly saved review"
        assert response.json()["brief_saved_at"] == saved_at
        stored = service.store.get(record.id, "owner")
        assert stored.brief_text == "Newer explicitly saved review" and stored.brief_saved_at == saved_at
        assert service.store.provenance(record.id, "owner") == ("cloud", "cloud")


def test_mixed_cloud_result_and_evidence_draft_survives_revocation_export_and_conversion(assistant_app, monkeypatch):
    from app.api import routes_assistant
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(loaded, AnalysisRequest(**payload(), experiment_id="uploaded"), "owner", True))
    record.brief_text = "Proven evidence-only saved notes"
    record.brief_saved_at = time.time()
    service.store.save(record, "owner")
    record.result.mode = "ai"
    record.result.summary = "Revoked private cloud interpretation"
    service.store.save(record, "owner")
    assert service.store.provenance(record.id, "owner") == ("cloud", "evidence")
    asyncio.run(service.revoke("owner", "uploaded"))
    path = f"/api/assistant/analyses/{record.id}"
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(assistant_app) as client:
        safe = client.get(path).json()
        assert safe["brief_text"] == record.brief_text and safe["result"]["mode"] == "evidence"
        exported = client.get(path + "/export")
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            document = archive.read("review-brief.html").decode()
            assert "Proven evidence-only saved notes" in document
            assert "Revoked private cloud" not in document
        review = client.post(path + "/review", headers=headers)
        assert review.status_code == 200
        assert review.json()["brief_text"] == record.brief_text
        assert review.json()["brief_saved_at"] == record.brief_saved_at
        assert review.json()["result"]["mode"] == "evidence"
        assert service.store.revoked(record.id, "owner")
        assert service.store.provenance(record.id, "owner") == ("evidence", "evidence")
        # Read-only conversion is safe; old draft-write capability remains permanently revoked.
        assert client.post(path + "/brief", headers=headers, json={"text": "Stale cloud autosave"}).status_code == 403
        service.store.set_consent("owner", "uploaded", True)
        assert client.post(path + "/brief", headers=headers, json={"text": "Stale cloud autosave"}).status_code == 403
        assert service.store.get(record.id, "owner").brief_text == record.brief_text
        # Public expiry and owner checks still apply before the safe-draft exception.
        with service.store.connect() as db:
            db.execute("UPDATE analyses SET public=1,payload=json_set(payload,'$.created_at',?) WHERE id=?", (time.time() - 86401, record.id))
        assert client.get(path + "/export").status_code == 404
        assert client.post(path + "/review", headers=headers).status_code == 404
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "stranger")
    with TestClient(assistant_app) as other:
        assert other.get(path + "/export").status_code == 404


def test_revocation_during_conversion_cannot_publish_a_stale_cloud_result(assistant_app, monkeypatch):
    from app.api import routes_assistant
    from app.assistant import evidence
    service = assistant_app.state.assistant
    loaded = load_bundle(get_settings().bundle_path).model_copy(update={"experiment_id": "uploaded"})
    monkeypatch.setattr(routes_assistant, "bundle", lambda *args: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *args: True)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *args: "owner")
    record = asyncio.run(service.create(loaded, AnalysisRequest(**payload(), experiment_id="uploaded"), "owner", True))
    record.brief_text = "Retain evidence-only notes"
    service.store.save(record, "owner")
    record.result.mode = "ai"
    service.store.save(record, "owner")
    service.store.set_consent("owner", "uploaded", True)
    original_convert = evidence.with_brief
    def revoke_during_convert(result, context):
        service.store.revoke_results("owner", "uploaded")
        return original_convert(result, context)
    monkeypatch.setattr(evidence, "with_brief", revoke_during_convert)
    with TestClient(assistant_app) as client:
        response = client.post(f"/api/assistant/analyses/{record.id}/review", headers={"X-Sidekick-Request": "1"})
        assert response.status_code == 403
        stored = service.store.get(record.id, "owner")
        assert stored.result is None and stored.brief_text == record.brief_text
