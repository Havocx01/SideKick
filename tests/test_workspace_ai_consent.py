"""Workspace AI approval persists independently of browser ownership."""
import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_assistant
from app.assistant.schemas import AnalysisRequest
from app.assistant.service import AssistantService
from app.assistant.store import AssistantStore
from app.config import get_settings
from app.evidence.bundle import load_bundle


def test_workspace_approval_covers_contexts_and_browsers_and_survives_restart(local_settings, monkeypatch):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=True, openai_api_key="mock-only", assistant_model="fixture",
        assistant_presenter_code="", assistant_tasks=("investigate", "data"), assistant_timeout_seconds=1)
    service = AssistantService(settings)
    app = FastAPI()
    app.state.assistant = service
    app.include_router(routes_assistant.router)
    loaded = load_bundle(get_settings().bundle_path)
    monkeypatch.setattr(routes_assistant, "bundle", lambda *_: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *_: True)
    monkeypatch.setattr(routes_assistant, "dataset_context", lambda *_: {"source": "upload"})
    service.store.set_consent("legacy-owner", "first", True)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(app) as first, TestClient(app) as second:
        assert not first.get("/api/assistant/consent/workspace").json()["allowed"]
        assert not first.get("/api/assistant/capabilities").json()["live_available"]
        assert first.post("/api/assistant/consent/workspace", json={"allowed": True}).status_code == 403
        assert first.post("/api/assistant/consent/workspace", json={"allowed": True},
                          headers={**headers, "Origin": "https://other.example"}).status_code == 403
        assert first.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=headers).status_code == 200
        for params in ({}, {"experiment_id": "first"}, {"experiment_id": "future"}, {"dataset_id": "future-upload"}):
            caps = second.get("/api/assistant/capabilities", params=params).json()
            assert not caps["live_available"] and caps["consent_granted"] and caps["consent_required"]
        service.store = AssistantStore(service.store.path.parent)
        assert second.get("/api/assistant/consent/workspace").json()["allowed"]
        assert second.post("/api/assistant/consent/workspace", json={"allowed": False}, headers=headers).status_code == 200
        assert not first.get("/api/assistant/capabilities", params={"experiment_id": "future"}).json()["live_available"]
        for mode in ("demo", "replay"):
            settings.mode = mode
            assert second.get("/api/assistant/consent/workspace").status_code == 403
            assert second.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=headers).status_code == 403


def test_workspace_revocation_clears_all_origins_before_cancellation(local_settings, monkeypatch):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="fixture", assistant_tasks=("investigate",))
    service = AssistantService(settings)
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"])
    cloud = asyncio.run(service.create(loaded, context, "first-owner", False))
    cloud.result.mode = "ai"
    cloud.brief_text = "Cloud-derived notes"
    service.store.save(cloud, "first-owner")
    safe = asyncio.run(service.create(loaded.model_copy(update={"experiment_id": "second"}), context.model_copy(update={"experiment_id": "second"}), "second-owner", False))
    safe.brief_text = "Evidence-only notes"
    service.store.save(safe, "second-owner")
    unknown = asyncio.run(service.create(loaded.model_copy(update={"experiment_id": "third"}), context.model_copy(update={"experiment_id": "third"}), "third-owner", False))
    unknown.brief_text = "Unknown-origin notes"
    service.store.save(unknown, "third-owner")
    with service.store.connect() as db:
        db.execute("UPDATE analysis_provenance SET result_origin='unknown',brief_origin='unknown' WHERE id=?", (unknown.id,))
    service.store.set_workspace_consent(True)
    service.contexts[cloud.id] = ("first-owner", None, False)

    async def cancel(id, owner):
        assert service.store.workspace_consent() is False
        assert service.store.get(cloud.id, "first-owner").result is None
        assert service.store.get(unknown.id, "third-owner").brief_text is None
    monkeypatch.setattr(service, "cancel", cancel)
    asyncio.run(service.revoke_workspace())
    restarted = AssistantStore(service.store.path.parent)
    assert restarted.workspace_consent() is False
    assert restarted.get(safe.id, "second-owner").brief_text == "Evidence-only notes"
    assert restarted.get(safe.id, "second-owner").error is None
    assert restarted.get(safe.id, "second-owner").updated_at == safe.updated_at
    assert not restarted.revoked(safe.id, "second-owner")
    assert restarted.revoked(cloud.id, "first-owner") and restarted.revoked(unknown.id, "third-owner")
    restarted.set_workspace_consent(True)
    assert restarted.get(cloud.id, "first-owner").brief_text is None


def test_restart_repairs_legacy_consent_notice_only_for_proven_local_records(local_settings):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="fixture", assistant_tasks=("investigate",))
    service = AssistantService(settings)
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path),
        AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"]), "owner", False))
    record.brief_text = "Retain engineer edits."
    record.error = "Cloud consent was revoked. Showing recorded evidence."
    service.store.save(record, "owner")
    restarted = AssistantStore(service.store.path.parent)
    repaired = restarted.get(record.id, "owner")
    assert repaired.error is None
    assert repaired.result == record.result and repaired.brief_text == record.brief_text
    assert repaired.updated_at == record.updated_at
    # A real tombstone is never removed or reclassified by the repair.
    with restarted.connect() as db:
        db.execute("UPDATE analyses SET payload=? WHERE id=?", (record.model_dump_json(), record.id))
        db.execute("UPDATE analysis_provenance SET revoked=1 WHERE id=?", (record.id,))
    guarded = AssistantStore(service.store.path.parent)
    assert guarded.get(record.id, "owner").error == record.error
    assert guarded.revoked(record.id, "owner")


def test_internal_legacy_provider_requires_permission_and_reuses_ai(local_settings, monkeypatch):
    from app.assistant import provider
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=True, openai_api_key="mock-only", assistant_model="fixture",
        assistant_tasks=("investigate", "brief"), assistant_timeout_seconds=1)
    service = AssistantService(settings)
    loaded = load_bundle(get_settings().bundle_path)
    context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"])
    calls = []

    async def enhance(result, *_args, **_kwargs):
        calls.append(1)
        return result.model_copy(update={"mode": "ai"})
    monkeypatch.setattr(provider, "enhance_analysis", enhance)

    async def check():
        local = await service._create_legacy_live(loaded, context, "owner", False, reuse=True)
        assert local.result.mode == "evidence" and not calls
        service.store.set_workspace_consent(True)
        active = await service._create_legacy_live(loaded, context, "owner", False, reuse=True)
        assert active.id != local.id and active.status == "running"
        await service.tasks[active.id]
        same = await service._create_legacy_live(loaded, context.model_copy(update={"task": "brief"}), "owner", False, reuse=True)
        assert same.id == active.id and same.result.mode == "ai" and calls == [1]
    asyncio.run(check())


def test_workspace_revocation_cancels_real_pending_job_without_late_output(local_settings, monkeypatch):
    from app.assistant import provider
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=True, openai_api_key="mock-only", assistant_model="fixture",
        assistant_tasks=("investigate",), assistant_timeout_seconds=2)
    service = AssistantService(settings)
    service.store.set_workspace_consent(True)
    entered = asyncio.Event()

    async def enhance(result, *_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(provider, "enhance_analysis", enhance)

    async def check():
        record = await service._create_legacy_live(load_bundle(get_settings().bundle_path),
            AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"]), "owner", False)
        await entered.wait()
        await service.revoke_workspace()
        assert not service.tasks and not service.contexts
        assert service.store.get(record.id, "owner").status == "cancelled"
        assert service.store.revoked(record.id, "owner")
        assert service.live_reason("another-owner", "future", False)
    asyncio.run(check())


def test_workspace_revocation_scrubs_unknown_future_contract_without_losing_identity(local_settings):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="fixture", assistant_tasks=("investigate",))
    service = AssistantService(settings)
    record = asyncio.run(service.create(load_bundle(get_settings().bundle_path),
        AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"]), "owner", False))
    record.result.mode = "ai"
    record.brief_text = "Historical cloud notes"
    service.store.save(record, "owner")
    raw = record.model_dump(mode="json")
    raw["context"]["task"] = "future-contract"
    raw["status"] = "running"
    with service.store.connect() as db:
        db.execute("UPDATE analyses SET payload=? WHERE id=?", (json.dumps(raw), record.id))
    asyncio.run(service.revoke_workspace())
    with service.store.connect() as db:
        owner, stored = db.execute("SELECT owner,payload FROM analyses WHERE id=?", (record.id,)).fetchone()
    saved = json.loads(stored)
    assert owner == "owner" and saved["id"] == record.id and saved["cache_fingerprint"] == record.cache_fingerprint
    assert saved["result"] is None and saved["brief_text"] is None and saved["status"] == "cancelled"
    assert service.store.revoked(record.id, "owner")


def test_workspace_revoke_denies_cloud_reads_conversion_export_and_reuse_for_all_owners(local_settings, monkeypatch):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=False, openai_api_key="", assistant_model="fixture", assistant_presenter_code="",
        assistant_tasks=("investigate", "brief"))
    service = AssistantService(settings)
    app = FastAPI()
    app.state.assistant = service
    app.include_router(routes_assistant.router)
    loaded = load_bundle(get_settings().bundle_path)
    monkeypatch.setattr(routes_assistant, "bundle", lambda _request, experiment=None: loaded.model_copy(update={"experiment_id": experiment}))
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *_: True)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(app) as first, TestClient(app) as second:
        first.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=headers)
        records = []
        for client, experiment in ((first, "first"), (second, "second")):
            response = client.post("/api/assistant/analyses", json={"task": "investigate",
                "experiment_id": experiment, "candidates": ["logistic_regression/lr1"]}, headers=headers)
            assert response.status_code == 200
            id = response.json()["id"]
            with service.store.connect() as db:
                owner = db.execute("SELECT owner FROM analyses WHERE id=?", (id,)).fetchone()[0]
            record = service.store.get(id, owner)
            record.result.mode = "ai"
            record.brief_text = "Cloud-derived private notes"
            service.store.save(record, owner)
            records.append((client, record))
            assert client.get(f"/api/assistant/analyses/{id}").json()["result"]["mode"] == "ai"
        assert first.get(f"/api/assistant/analyses/{records[1][1].id}").status_code == 404
        assert second.post("/api/assistant/consent/workspace", json={"allowed": False}, headers=headers).status_code == 200
        for client, record in records:
            path = f"/api/assistant/analyses/{record.id}"
            response = client.get(path)
            assert response.json()["result"]["mode"] == "evidence"
            assert "Cloud-derived private notes" not in response.text
            assert client.post(path + "/review", headers=headers).status_code == 403
            assert client.get(path + "/export").status_code == 403
        first.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=headers)
        record = records[0][1]
        new = first.post("/api/assistant/analyses?reuse=true", json=record.context.model_dump(mode="json"), headers=headers).json()
        assert new["id"] != record.id and new["brief_text"] is None
