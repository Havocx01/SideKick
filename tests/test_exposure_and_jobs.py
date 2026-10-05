import time
from uuid import uuid4

import pytest
from app.experiments.store import Workspace


def record(id=None, status="queued"):
    return {"experiment_id": id or str(uuid4()), "status": status, "created_at": time.time(), "started_at": None, "finished_at": None}


def test_atomic_validation_claim_and_exposure(tmp_path):
    workspace = Workspace(tmp_path)
    parent, operation_id = str(uuid4()), str(uuid4())
    job = record()
    job.update(parent_experiment_id=parent, operation_id=operation_id)
    operation = {"job_id": job["experiment_id"], "exposure_started_at": None}
    workspace.reserve_operation(job, operation, "validation")
    workspace.expose(["one", "two"], parent, "Scoring", validation_id=operation_id)
    assert workspace.operation(parent, "validation")["exposure_started_at"] is not None
    with pytest.raises(ValueError):
        workspace.expose(["one", "two"], parent, "Repeat", validation_id=operation_id)
    workspace.update(job["experiment_id"], status="interrupted", finished_at=time.time())
    new_job = record()
    new_job.update(parent_experiment_id=parent, operation_id=str(uuid4()))
    with pytest.raises(ValueError):
        workspace.reserve_operation(new_job, {"job_id": new_job["experiment_id"]}, "validation")


def test_restart_marks_active_jobs_interrupted(tmp_path):
    workspace = Workspace(tmp_path)
    job = record()
    workspace.reserve(job)
    workspace.recover()
    assert workspace.get("experiments", job["experiment_id"])["status"] == "interrupted"


def test_one_active_job_and_retry_before_exposure(tmp_path):
    workspace = Workspace(tmp_path)
    parent = str(uuid4())
    job = record()
    job.update(parent_experiment_id=parent, operation_id=str(uuid4()))
    workspace.reserve_operation(job, {"job_id": job["experiment_id"], "exposure_started_at": None}, "validation")
    with pytest.raises(ValueError):
        workspace.reserve(record())
    workspace.update(job["experiment_id"], status="cancelled")
    retry = record()
    retry.update(parent_experiment_id=parent, operation_id=str(uuid4()))
    workspace.reserve_operation(retry, {"job_id": retry["experiment_id"], "exposure_started_at": None}, "validation")
    assert workspace.operation(parent, "validation")["job_id"] == retry["experiment_id"]
