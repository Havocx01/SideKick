import subprocess
import sys
import time

import pytest
from app.experiments.datasets import sample
from app.experiments.jobs import Jobs
from app.schemas import ExperimentCreate


@pytest.mark.parametrize("action,expected", [("cancel", "cancelled"), ("timeout", "timed_out"), ("shutdown", "interrupted")])
def test_worker_is_stopped_and_status_persists(local_settings, monkeypatch, action, expected):
    original = subprocess.Popen
    processes = []

    def start_process(args, **options):
        process = original([sys.executable, "-c", "import time; time.sleep(60)"], **options)
        processes.append(process)
        return process

    monkeypatch.setattr("app.experiments.jobs.subprocess.Popen", start_process)
    root = local_settings / "lifecycle"
    jobs = Jobs(root, timeout_seconds=.5 if action == "timeout" else 900)
    try:
        data = sample(jobs.workspace, hosted=True)
        job = jobs.create(ExperimentCreate(dataset_id=data.dataset_id))
        deadline = time.monotonic() + 10
        while not processes and time.monotonic() < deadline:
            time.sleep(.02)
        assert processes
        if action == "cancel":
            jobs.cancel(job.experiment_id)
        elif action == "shutdown":
            jobs.close()
        while jobs.workspace.get("experiments", job.experiment_id)["status"] != expected and time.monotonic() < deadline:
            time.sleep(.02)
        assert jobs.workspace.get("experiments", job.experiment_id)["status"] == expected
        assert processes[0].poll() is not None
    finally:
        jobs.close()
    with_jobs = Jobs(root)
    try:
        assert with_jobs.workspace.get("experiments", job.experiment_id)["status"] == expected
    finally:
        with_jobs.close()
