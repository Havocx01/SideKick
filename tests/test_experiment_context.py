"""Context is editable metadata, never recorded training or scoring evidence."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.experiments.store import Workspace
from app.assistant.schemas import AnalysisRequest
from test_deep_investigation import deep_app as deep_app, fake_provider, completed

HEADERS = {"X-Sidekick-Request": "1"}


def context_client(deep_app, tmp_path):
    app, loaded = deep_app
    workspace = Workspace(tmp_path / "context")
    app.state.jobs = SimpleNamespace(workspace=workspace)
    return TestClient(app), app, workspace, loaded


def test_context_save_restart_clear_and_evidence_unchanged(deep_app, tmp_path):
    client, _, workspace, loaded = context_client(deep_app, tmp_path)
    before = loaded.model_dump_json()
    with client:
        assert client.get("/api/assistant/experiment-context").json() == {"equipment_type": "", "sensor_meaning": "", "decision": ""}
        fields = {"equipment_type": " Cooling pump ", "sensor_meaning": "Bearing temperature", "decision": "Review missing warnings"}
        saved = client.post("/api/assistant/experiment-context", json=fields, headers=HEADERS)
        assert saved.status_code == 200
        assert saved.json()["equipment_type"] == "Cooling pump"
        assert Workspace(workspace.root).engineer_context(None)["decision"] == fields["decision"]
        assert client.get("/api/assistant/experiment-context").json() == saved.json()
        assert client.post("/api/assistant/experiment-context", json={}, headers=HEADERS).json()["decision"] == ""
        assert client.get("/api/assistant/experiment-context").json()["equipment_type"] == ""
    assert loaded.model_dump_json() == before


def test_context_origin_validation_modes_and_unknown_records(deep_app, tmp_path):
    client, app, workspace, _ = context_client(deep_app, tmp_path)
    with client:
        assert client.post("/api/assistant/experiment-context", json={}).status_code == 403
        assert client.post("/api/assistant/experiment-context", json={}, headers={**HEADERS, "Origin": "https://other.test"}).status_code == 403
        assert client.post("/api/assistant/experiment-context", json={"sensor_meaning": "x" * 501}, headers=HEADERS).status_code == 422
        assert client.get(f"/api/assistant/experiment-context?experiment_id={uuid4()}").status_code == 404
        for mode in ("demo", "replay"):
            app.state.assistant.settings.mode = mode
            assert client.get("/api/assistant/experiment-context").status_code == 403
            assert client.post("/api/assistant/experiment-context", json={}, headers=HEADERS).status_code == 403
    assert workspace.engineer_context(None) is None


def test_pretraining_context_reserved_separately_and_original_payload_unchanged(tmp_path):
    workspace = Workspace(tmp_path)
    record = {"experiment_id": str(uuid4()), "dataset_id": str(uuid4()), "status": "completed", "created_at": 1}
    fields = {"equipment_type": "Pump", "sensor_meaning": "Temperature", "decision": "Review warnings"}
    workspace.reserve(record, engineer_context=fields)
    assert workspace.get("experiments", record["experiment_id"]) == record
    assert Workspace(tmp_path).engineer_context(record["experiment_id"]) == fields


def test_focus_validation_and_empty_identity_compatibility(deep_app):
    app, loaded = deep_app
    body = {"task": "deep", "candidates": ["xgboost_augmented/aug3"]}
    empty = AnalysisRequest.model_validate({**body, "investigation_focus": "  "})
    default = AnalysisRequest.model_validate(body)
    focused = AnalysisRequest.model_validate({**body, "investigation_focus": " Review missing warnings "})
    assert empty.investigation_focus is None
    assert focused.investigation_focus == "Review missing warnings"
    assert app.state.assistant.identities(loaded, empty, True) == app.state.assistant.identities(loaded, default, True)
    assert app.state.assistant.identities(loaded, focused, True) != app.state.assistant.identities(loaded, default, True)
    with pytest.raises(ValueError):
        AnalysisRequest.model_validate({**body, "task": "investigate", "investigation_focus": "Question"})


def test_deep_uses_saved_context_snapshot_and_edits_do_not_launch_ai(deep_app, tmp_path, monkeypatch):
    client, app, _, _ = context_client(deep_app, tmp_path)
    app.state.assistant.store.set_workspace_consent(True)
    calls = fake_provider(monkeypatch)
    body = {"task": "deep", "candidates": ["logistic_regression/lr2"], "investigation_focus": "Review delayed warnings"}
    with client:
        fields = {"equipment_type": "Cooling pump", "decision": "Review delayed warnings"}
        client.post("/api/assistant/experiment-context", json=fields, headers=HEADERS).raise_for_status()
        assert len(calls) == 0
        started = client.post("/api/assistant/analyses?reuse=true", json=body, headers=HEADERS).json()
        record = completed(client, started["id"])
        assert record["context"]["engineer_context"]["equipment_type"] == "Cooling pump"
        assert record["context"]["investigation_focus"] == body["investigation_focus"]
        reopened = client.post("/api/assistant/analyses?reuse=true", json=body, headers=HEADERS).json()
        assert reopened["id"] == record["id"] and len(calls) == 1
        client.post("/api/assistant/experiment-context", json={}, headers=HEADERS).raise_for_status()
        assert len(calls) == 1
        assert client.get(f"/api/assistant/analyses/{record['id']}").json()["context"]["engineer_context"]["equipment_type"] == "Cooling pump"
