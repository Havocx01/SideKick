"""Public routine actions never admit provider work, even with permission and a key."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_assistant
from app.assistant.schemas import AnalysisRecord
from app.assistant.service import AssistantService
from app.config import get_settings
from app.evidence.bundle import load_bundle


@pytest.fixture
def routine_app(local_settings, monkeypatch):
    settings = SimpleNamespace(artifacts_dir=local_settings, mode="full", assistant_enabled=True,
        assistant_live_enabled=True, nebius_base_url="https://api.tokenfactory.nebius.com/v1/", nebius_api_key="mock-only", assistant_model="fixture",
        assistant_presenter_code="presenter", assistant_timeout_seconds=1,
        assistant_tasks=("investigate", "compare", "warning", "brief", "data"))
    app = FastAPI()
    app.state.assistant = AssistantService(settings)
    app.state.assistant.allow_workspace()
    app.include_router(routes_assistant.router)
    loaded = load_bundle(get_settings().bundle_path)
    monkeypatch.setattr(routes_assistant, "bundle", lambda *_: loaded)
    monkeypatch.setattr(routes_assistant, "upload_context", lambda *_: False)
    monkeypatch.setattr(routes_assistant, "visitor", lambda *_: "owner")
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(1)
        raise AssertionError("Routine actions must not invoke the provider")
    monkeypatch.setattr("app.assistant.provider.enhance_analysis", forbidden)
    return app, loaded, calls


@pytest.mark.parametrize("mode", ["full", "demo", "replay"])
@pytest.mark.parametrize("task", ["investigate", "compare", "warning", "brief"])
def test_every_routine_model_action_is_local_and_reuses_saved_output(routine_app, task, mode):
    app, loaded, calls = routine_app
    app.state.assistant.settings.mode = mode
    app.state.assistant.store.unlock("owner")
    body = {"task": task, "candidates": ["logistic_regression/lr1"]}
    if task == "compare":
        body["candidates"].append("logistic_regression/lr2")
    if task == "warning":
        series = next(series for series in loaded.replay_series if series.points)
        body.update(candidates=[f"{series.candidate.value}/{series.config_id}"], partition=series.partition.value,
                    equipment_id=series.equipment_id, scenario_id=series.scenario_id, cycle=series.points[0].cycle)
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(app) as client:
        caps = client.get("/api/assistant/capabilities").json()
        assert not caps["live_available"] and not caps["unlock_available"]
        response = client.post("/api/assistant/analyses?reuse=true", json=body, headers=headers)
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["status"] == "completed" and record["result"]["mode"] == "evidence"
        assert record["result"]["fallback_reason"] is None and record["result"]["model"] is None
        assert record["result"]["assessment"] and record["result"]["sources"]
        same = client.post("/api/assistant/analyses?reuse=true", json=body, headers=headers).json()
        assert same["id"] == record["id"] and same["reused"]
        review = client.post(f"/api/assistant/analyses/{record['id']}/review", headers=headers)
        assert review.status_code == 200 and review.json()["id"] == record["id"]
        fresh = client.post("/api/assistant/analyses", json=body, headers=headers).json()
        assert fresh["status"] == "completed" and fresh["result"]["mode"] == "evidence"
        assert fresh["id"] != record["id"]
    assert calls == [] and not app.state.assistant.tasks


def test_saved_cloud_output_is_preserved_and_reused_without_generation(routine_app):
    app, loaded, calls = routine_app
    body = {"task": "investigate", "candidates": ["logistic_regression/lr1"]}
    headers = {"X-Sidekick-Request": "1"}
    with TestClient(app) as client:
        original = client.post("/api/assistant/analyses", json=body, headers=headers).json()
        record = AnalysisRecord.model_validate(original)
        record.result.mode = "ai"
        record.result.model = "saved-model"
        record.brief_text = "Engineer-edited saved cloud notes"
        record.cache_fingerprint = app.state.assistant.identities(loaded, record.context, True)[0]
        app.state.assistant.store.save(record, "owner")
        path = f"/api/assistant/analyses/{record.id}"
        before = client.get(path).json()
        reopened = client.post("/api/assistant/analyses?reuse=true", json=body, headers=headers).json()
        assert reopened["id"] == record.id and reopened["result"]["mode"] == "ai"
        assert reopened["brief_text"] == before["brief_text"] == record.brief_text
        assert client.post(path + "/review", headers=headers).status_code == 200
        assert client.post(path + "/brief", headers=headers, json={"text": record.brief_text}).status_code == 200
        assert client.get(path + "/export").status_code == 200
        client.post("/api/assistant/consent/workspace", headers=headers, json={"allowed": False})
        denied = client.get(path)
        assert denied.json()["result"]["mode"] == "evidence"
        assert record.brief_text not in denied.text and client.get(path + "/export").status_code == 403
        with app.state.assistant.store.connect() as db:
            stored = json.loads(db.execute("SELECT payload FROM analyses WHERE id=?", (record.id,)).fetchone()[0])
        assert stored["brief_text"] is None
    assert calls == []


def test_public_request_cannot_enable_the_internal_provider(routine_app):
    app, _, calls = routine_app
    with TestClient(app) as client:
        response = client.post("/api/assistant/analyses", headers={"X-Sidekick-Request": "1"},
            json={"task": "investigate", "candidates": ["logistic_regression/lr1"], "live": True})
        assert response.status_code == 422
    assert calls == []


def test_csv_review_is_local_and_keeps_mapping_and_dataset_unchanged(routine_app, tmp_path, monkeypatch):
    from app.data.synthetic import make_synthetic_dataset
    from app.experiments.datasets import register
    from app.experiments.store import Workspace
    from uuid import uuid4
    app, _, calls = routine_app
    workspace = Workspace(tmp_path / "csv-fixture")
    id = str(uuid4())
    path = workspace.directory("datasets", id) / "data.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    make_synthetic_dataset().frame.to_csv(path, index=False)
    dataset = register(workspace, path, id, "fixture.csv")
    before = workspace.get("datasets", id)
    app.state.jobs = SimpleNamespace(workspace=workspace)
    monkeypatch.setattr(routes_assistant, "dataset_context", lambda *_: before)
    body = {"task": "data", "dataset_id": id, "mapping": dataset.mapping.model_dump(mode="json")}
    with TestClient(app) as client:
        response = client.post("/api/assistant/analyses?reuse=true", headers={"X-Sidekick-Request": "1"}, json=body)
        assert response.status_code == 200, response.text
        record = response.json()
        assert record["status"] == "completed" and record["result"]["mode"] == "evidence"
        assert record["result"]["fallback_reason"] is None and record["result"]["suggested_mapping"]
        assert workspace.get("datasets", id) == before
        assert client.get(f"/api/assistant/analyses/{record['id']}").status_code == 200
    assert not calls and not app.state.assistant.tasks


def test_permission_changes_never_upgrade_or_replace_a_routine_saved_answer(routine_app):
    app, _, calls = routine_app
    headers = {"X-Sidekick-Request": "1"}
    body = {"task": "investigate", "candidates": ["logistic_regression/lr1"]}
    with TestClient(app) as client:
        client.post("/api/assistant/consent/workspace", json={"allowed": False}, headers=headers)
        first = client.post("/api/assistant/analyses?reuse=true", json=body, headers=headers).json()
        client.post("/api/assistant/consent/workspace", json={"allowed": True}, headers=headers)
        reopened = client.post("/api/assistant/analyses?reuse=true", json=body, headers=headers).json()
        assert reopened["id"] == first["id"] and reopened["result"] == first["result"]
        assert reopened["result"]["fallback_reason"] is None
    assert calls == []


def test_routine_creation_does_not_join_an_active_legacy_provider_job(routine_app, monkeypatch):
    from app.assistant.schemas import AnalysisRequest
    app, loaded, _ = routine_app
    service = app.state.assistant
    calls = []

    async def check():
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def legacy(result, *args, **kwargs):
            calls.append(1)
            entered.set()
            await gate.wait()
            return result.model_copy(update={"mode": "ai"})
        monkeypatch.setattr("app.assistant.provider.enhance_analysis", legacy)
        context = AnalysisRequest(task="investigate", candidates=["logistic_regression/lr1"])
        old = await service._create_legacy_live(loaded, context, "owner", False, reuse=True)
        await entered.wait()
        regular = await service.create(loaded, context, "owner", False, reuse=True)
        assert regular.id != old.id and regular.status == "completed" and regular.result.mode == "evidence"
        assert old.id in service.tasks and calls == [1]
        gate.set()
        await asyncio.gather(*service.tasks.values())
    asyncio.run(check())
