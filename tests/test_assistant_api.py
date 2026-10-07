"""Assistant boundary tests use recorded evidence and mocked cloud calls only."""
import asyncio
import io
import json
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes_assistant import router
from app.assistant.service import AssistantService
from app.assistant.schemas import AnalysisRequest
from app.assistant.store import AssistantStore
from app.evidence.bundle import load_bundle
from app.config import get_settings


@pytest.fixture
def assistant_app(local_settings):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="test", assistant_presenter_code="",
        assistant_timeout_seconds=0.02, assistant_session_limit=10, assistant_daily_limit=25,
        assistant_tasks=("investigate", "compare", "warning", "brief"))
    app = FastAPI()
    app.state.assistant = AssistantService(settings)
    app.include_router(router)
    return app


def payload():
    return {"task": "investigate", "candidates": ["logistic_regression/lr1"]}


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


def test_public_evidence_allowance_is_rate_limited(assistant_app, monkeypatch):
    from app.assistant.store import PublicLimitError
    service = assistant_app.state.assistant
    monkeypatch.setattr(service.settings, "mode", "demo")

    def exhausted(owner):
        raise PublicLimitError("Analysis allowance reached. Try again in an hour.")

    monkeypatch.setattr(service.store, "admit_evidence", exhausted)

    @assistant_app.middleware("http")
    async def demo_session(request, call_next):
        request.state.demo_token = "default-test-session"
        return await call_next(request)
    with TestClient(assistant_app) as client:
        response = client.post("/api/assistant/analyses", json=payload(), headers={"X-Sidekick-Request": "1"})
    assert response.status_code == 429
    assert "allowance" in response.json()["detail"]


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


def test_atomic_quota_and_access_throttle(tmp_path):
    store = AssistantStore(tmp_path)
    store.admit("one", 1, 2)
    with pytest.raises(ValueError):
        store.admit("one", 1, 2)
    store.admit("two", 1, 2)
    with pytest.raises(ValueError):
        store.admit("three", 1, 2)
    for _ in range(5):
        store.attempt("host")
    with pytest.raises(ValueError):
        store.attempt("host")


def test_rejected_ai_output_falls_back_to_recorded_evidence(assistant_app, monkeypatch):
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "test-not-a-real-key"
    async def invalid(result, context, settings):
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


def test_timeout_cancel_consent_and_restart(assistant_app, monkeypatch):
    from app.assistant import provider
    assistant = assistant_app.state.assistant
    assistant.settings.assistant_live_enabled = True
    assistant.settings.openai_api_key = "test-not-a-real-key"
    calls = []
    async def slow(result, context, settings):
        calls.append(context)
        await asyncio.sleep(10)
        return result
    monkeypatch.setattr(provider, "enhance_analysis", slow)
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(**payload())

    async def run():
        record = await assistant.create(loaded, context, "owner", False)
        await asyncio.sleep(0.05)
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

