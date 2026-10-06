import time
from dataclasses import replace

import pytest
from app.config import EXPERIMENT
from app.experiments.datasets import sample
from fastapi.testclient import TestClient


def wait(client, id, expected="completed"):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = client.get(f"/api/experiments/{id}")
        assert response.status_code == 200, response.text
        record = response.json()
        if record["status"] not in ("queued", "running", "cancelling"):
            assert record["status"] == expected, record
            return record
        time.sleep(.2)
    raise AssertionError("Worker did not finish within the test deadline")


@pytest.mark.integration
def test_training_freeze_validation_and_exports(local_settings, monkeypatch):
    from app.experiments import protocol
    from app.main import create_app

    monkeypatch.setattr(protocol, "EXPERIMENT", replace(EXPERIMENT, configs_per_candidate=1))
    application = create_app()
    with TestClient(application) as client:
        dataset = sample(application.state.jobs.workspace, hosted=True)
        response = client.post("/api/experiments", json={"dataset_id": dataset.dataset_id, "min_detection_fraction": 0, "max_early_alarm_burden": 1})
        assert response.status_code == 201, response.text
        id = response.json()["experiment_id"]
        wait(client, id)
        selected = client.get("/api/selection", params={"experiment_id": id}).json()
        assert selected["recommended"] is not None
        recommendation = selected["recommended"]
        key = recommendation["candidate"] + "/" + recommendation["config_id"]
        replay = client.get("/api/replay/index", params={"experiment_id": id, "candidate": key}).json()
        assert replay["series"]
        assert all(s["candidate"] + "/" + s["config_id"] == key for s in replay["series"])
        agreement = {"brief": {"equipment_family": "Simulated demonstration family", "reviewing_engineer": "Test reviewer",
            "current_procedure": "Manual metric review", "intended_decision": "Choose whether to investigate a model",
            "success_measure": "Documented review decision", "data_classification": "simulated"},
            "single_family_confirmed": True, "failure_labels_checked": True,
            "representative_data_confirmed": True, "protocol_agreed": True}
        assert client.post(f"/api/experiments/{id}/pilot/agreement", json=agreement).status_code == 201
        frozen = client.post(f"/api/experiments/{id}/freeze")
        assert frozen.status_code == 202, frozen.text
        wait(client, frozen.json()["job_id"])
        assert client.post(f"/api/experiments/{id}/freeze").status_code == 409
        from app.experiments import jobs
        original_digest = jobs.source_digest
        monkeypatch.setattr(jobs, "source_digest", lambda: "changed-source")
        assert client.post(f"/api/experiments/{id}/validation", json={"untouched_confirmed": True}).status_code == 409
        monkeypatch.setattr(jobs, "source_digest", original_digest)
        artifact = application.state.jobs.workspace.directory("experiments", frozen.json()["job_id"]) / "model.joblib"
        saved_artifact = artifact.read_bytes()
        artifact.write_bytes(b"changed")
        rejected = client.post(f"/api/experiments/{id}/validation", json={"untouched_confirmed": True})
        failed = wait(client, rejected.json()["job_id"], "failed")
        assert "artifact changed" in failed["error"]
        assert client.get(f"/api/experiments/{id}/validation").json()["record"]["exposure_started_at"] is None
        artifact.write_bytes(saved_artifact)
        assert client.post(f"/api/experiments/{id}/validation", json={"untouched_confirmed": False}).status_code == 409
        validation = client.post(f"/api/experiments/{id}/validation", json={"untouched_confirmed": True})
        assert validation.status_code == 202, validation.text
        wait(client, validation.json()["job_id"])
        final = client.get("/api/final-evaluation", params={"experiment_id": id}).json()
        assert final["available"]
        assert final["selection"]["ranked"][0]["clean"]["engines"] == 20
        review = client.post(f"/api/experiments/{id}/pilot/review", json={"reviewing_engineer": "Test reviewer",
            "decision": "collect_data", "decision_changed": True, "observations": "Request real histories before a field pilot.",
            "evidence_reviewed": True})
        assert review.status_code == 201, review.text
        assert review.json()["validation_id"] == validation.json()["validation_id"]
        assert client.get(f"/api/experiments/{id}/pilot").json()["phase"] == "complete"
        assert client.post(f"/api/experiments/{id}/validation", json={"untouched_confirmed": True}).status_code == 409
        export = client.get("/api/export", params={"experiment_id": id, "candidate": key, "partition": "holdout"})
        assert export.status_code == 200, export.text
        assert export.content[:4] == b"PK\x03\x04"
        assert ".zip" in export.headers["content-disposition"]
        assert len(client.get("/api/experiments").json()) == 1
        stricter = client.post("/api/experiments", json={"dataset_id": dataset.dataset_id,
            "min_detection_fraction": 1, "max_early_alarm_burden": 0})
        strict_id = stricter.json()["experiment_id"]
        wait(client, strict_id)
        strict = client.get("/api/selection", params={"experiment_id": strict_id}).json()
        assert strict["outcome"] == "none_qualified"
        assert client.post(f"/api/experiments/{strict_id}/freeze").status_code == 409
        assert client.get("/api/final-evaluation", params={"experiment_id": strict_id}).json()["available"] is False
