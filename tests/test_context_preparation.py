import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

from test_investigations_api import api as api
from test_compound_faults import fitted as fitted


def waitFor(client, id):
    for _ in range(300):
        response = client.get(f"/api/investigations/contexts/preparation/{id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] not in {"queued", "running", "cancelling"}:
            return job
        time.sleep(.05)
    pytest.fail("Context preparation did not finish")


@pytest.mark.parametrize("lockedProgress", [False, True])
def test_preparation_trains_and_publishes_a_new_context_without_provider_calls(api, lockedProgress):
    client, service, root = api
    from app.investigator import preparation
    original = {path.name: path.read_bytes() for path in (root / "contexts" / "synthetic").iterdir()}
    realPopen = preparation.subprocess.Popen
    bootstrap = "import runpy,socket,sys\ndef denied(*args,**kwargs): raise AssertionError('Training must stay offline')\nsocket.socket.connect=denied\nsocket.create_connection=denied\nsys.argv=sys.argv[1:]\nrunpy.run_module(sys.argv[0],run_name='__main__')"
    if lockedProgress:
        bootstrap = """from pathlib import Path
replace = Path.replace
def replaceProgress(self, target):
    if Path(target).name == 'progress.json' and Path(target).exists():
        raise PermissionError('Windows reader holds the progress file open')
    return replace(self, target)
Path.replace = replaceProgress
""" + bootstrap
    def offlineWorker(args, **kwargs):
        return realPopen([args[0], "-c", bootstrap, *args[2:]], **kwargs)
    with patch.object(preparation.subprocess, "Popen", offlineWorker):
        response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-sample-1"})
        assert response.status_code == 202, response.text
        job = waitFor(client, response.json()["id"])
    assert job["status"] == "completed", job
    assert job["context"] != "synthetic" and job["stage"] == "ready"
    assert {path.name: path.read_bytes() for path in (root / "contexts" / "synthetic").iterdir()} == original
    contexts = client.get("/api/investigations/contexts").json()
    context = next(item for item in contexts if item["name"] == job["context"])
    assert context["profile"] == "synthetic-rotating-v1" and all(row["histories"] == 22 for row in context["clean"].values())
    repeated = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-sample-1"}).json()
    assert repeated["id"] == job["id"] and repeated["status"] == "completed"
    assert client.get("/api/investigations/contexts/preparation").json()["job"]["id"] == job["id"]


def test_stale_packages_are_explained_and_preserved(api):
    client, service, root = api
    manifestPath = root / "contexts" / "synthetic" / "manifest.json"
    manifest = json.loads(manifestPath.read_text())
    manifest["source_digest"] = "0" * 64
    manifestPath.write_text(json.dumps(manifest))
    assert client.get("/api/investigations/contexts").json() == []
    state = client.get("/api/investigations/contexts/preparation").json()
    assert state["outdated"] == 1 and state["job"] is None
    assert manifestPath.exists()


def test_preparation_is_owned_and_only_available_in_full_mode(api, monkeypatch):
    client, service, root = api
    assert client.post("/api/investigations/contexts/preparation", json={"requestId": "../bad"}).status_code == 422
    assert client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-origin", "output": "/tmp/arbitrary"}).status_code == 422
    assert client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-origin"},
        headers={"Origin": "https://other.example"}).status_code == 403
    for mode in ["demo", "replay"]:
        monkeypatch.setenv("SIDEKICK_MODE", mode)
        from app.config import reset_settings
        reset_settings()
        assert client.get("/api/investigations/contexts/preparation").status_code == 403
        assert client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-mode"}).status_code == 403


def test_worker_removes_credentials_and_bounds_training(api, monkeypatch):
    client, service, root = api
    from app.investigator import preparation
    monkeypatch.setenv("NEBIUS_API_KEY", "must-not-reach-worker")
    monkeypatch.setenv("TAVILY_API_KEY", "must-not-reach-worker")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-worker")
    calls = []
    class FailedProcess:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))
        def poll(self):
            return 1
    monkeypatch.setattr(preparation.subprocess, "Popen", FailedProcess)
    response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-worker-1"})
    assert response.status_code == 202
    job = waitFor(client, response.json()["id"])
    assert job["status"] == "failed" and job["context"] is None
    args, options = calls[0]
    assert args[1:3] == ["-m", "app.investigator.preparation_worker"]
    assert all(key not in options["env"] for key in ["NEBIUS_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY"])
    assert options["env"]["SIDEKICK_MLFLOW"] == "0" and options["env"]["OMP_NUM_THREADS"] == "1"
    assert "must-not-reach-worker" not in json.dumps(job)
    assert [item["name"] for item in client.get("/api/investigations/contexts").json()] == ["synthetic"]


@pytest.fixture
def blockedWorker(monkeypatch):
    from app.investigator import preparation
    started, stopped = threading.Event(), threading.Event()
    class Process:
        def __init__(self, *_args, **_kwargs):
            started.set()
        def poll(self):
            return 1 if stopped.is_set() else None
        def terminate(self):
            stopped.set()
        def wait(self, **_kwargs):
            return 1
    monkeypatch.setattr(preparation.subprocess, "Popen", Process)
    return started, stopped


def test_prepare_is_nonblocking_idempotent_owned_and_cancellable(api, blockedWorker):
    client, service, root = api
    response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-alice-1"}, headers={"x-owner": "alice"})
    assert response.status_code == 202
    id = response.json()["id"]
    assert blockedWorker[0].wait(2)
    same = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-alice-1"}, headers={"x-owner": "alice"})
    assert same.json()["id"] == id
    assert client.get("/api/investigations/contexts/preparation", headers={"x-owner": "alice"}).json()["job"]["id"] == id
    assert client.get("/api/investigations/contexts/preparation", headers={"x-owner": "bob"}).json()["job"] is None
    assert client.get(f"/api/investigations/contexts/preparation/{id}", headers={"x-owner": "bob"}).status_code == 404
    assert client.post(f"/api/investigations/contexts/preparation/{id}/cancel", headers={"x-owner": "bob"}).status_code == 404
    assert client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-bob-1"}, headers={"x-owner": "bob"}).status_code == 409
    cancelled = client.post(f"/api/investigations/contexts/preparation/{id}/cancel", headers={"x-owner": "alice"})
    assert cancelled.json()["status"] == "cancelling" and cancelled.json()["context"] is None
    assert blockedWorker[1].wait(2)
    service.preparation.thread.join(2)
    assert service.preparation.get("alice", id).status == "cancelled"
    assert [item["name"] for item in client.get("/api/investigations/contexts").json()] == ["synthetic"]


def test_shutdown_stops_the_worker_and_restart_keeps_interrupted_status(api, blockedWorker):
    from app.investigator.service import InvestigationService
    client, service, root = api
    response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-restart"})
    id = response.json()["id"]
    assert blockedWorker[0].wait(2)
    service.close()
    assert blockedWorker[1].is_set()
    restarted = InvestigationService(root, service.settings)
    try:
        job = restarted.preparation.get("local", id)
        assert job.status == "interrupted" and job.context is None
        from app.investigator.schemas import ContextPreparationRequest
        same = restarted.preparation.start("local", ContextPreparationRequest(requestId="prepare-restart"))
        assert same.id == id and same.status == "interrupted"
        assert restarted.preparation.thread is None
    finally:
        restarted.close()


def test_preparation_timeout_stops_the_worker(api, blockedWorker):
    client, service, root = api
    service.preparation.timeout = .02
    response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-timeout"})
    job = waitFor(client, response.json()["id"])
    assert job["status"] == "failed" and "time limit" in job["error"]
    assert blockedWorker[1].wait(2)
    assert job["context"] is None


def test_malformed_context_metadata_does_not_break_preparation_status(api):
    client, service, root = api
    broken = root / "contexts" / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text("[]")
    state = client.get("/api/investigations/contexts/preparation")
    assert state.status_code == 200 and state.json()["outdated"] == 1
    assert (broken / "manifest.json").read_text() == "[]"


def test_cancel_holds_the_worker_slot_until_termination_finishes(api, monkeypatch):
    from app.investigator import preparation
    client, service, root = api
    started, terminating, release, stopped = (threading.Event() for _ in range(4))
    class Process:
        def __init__(self, *_args, **_kwargs):
            started.set()
        def poll(self):
            return 1 if stopped.is_set() else None
        def terminate(self):
            terminating.set()
            release.wait(5)
            stopped.set()
        def wait(self, **_kwargs):
            return 1
    monkeypatch.setattr(preparation.subprocess, "Popen", Process)
    response = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-slow-cancel"})
    id = response.json()["id"]
    assert started.wait(2)
    thread = service.preparation.thread
    client.post(f"/api/investigations/contexts/preparation/{id}/cancel")
    assert terminating.wait(2)
    try:
        retry = client.post("/api/investigations/contexts/preparation", json={"requestId": "prepare-after-cancel"})
        assert retry.status_code == 409 and service.preparation.thread is thread
        assert service.preparation.get("local", id).status == "cancelling"
    finally:
        release.set()
        thread.join(2)
    assert service.preparation.get("local", id).status == "cancelled"


def test_restart_recovers_a_published_context_if_the_status_commit_was_interrupted(api):
    from app.investigator.preparation import ContextPreparer
    from app.investigator.schemas import ContextPreparation
    client, service, root = api
    id = "a" * 32
    name = f"synthetic-{id[:12]}"
    shutil.copytree(root / "contexts" / "synthetic", root / "contexts" / name)
    job = ContextPreparation(id=id, status="running", stage="checking", createdAt=time.time())
    with service.store.transaction() as db:
        db.execute("INSERT INTO context_preparations VALUES(?,?,?,?,?,?)", (id, "local", "prepare-published", job.status, job.model_dump_json(), job.createdAt))
    recovered = ContextPreparer(root, service.store)
    try:
        restored = recovered.get("local", id)
        assert restored.status == "completed" and restored.context == name and restored.stage == "ready"
        assert recovered.thread is None
    finally:
        recovered.close()


@pytest.mark.parametrize("timeout,lifetime", [(.1, 60), (60, .1)])
def test_worker_exits_when_parent_heartbeat_stops_or_lifetime_is_exceeded(tmp_path, timeout, lifetime):
    (tmp_path / "heartbeat").touch()
    backend = Path(__file__).resolve().parents[1] / "backend"
    code = "from pathlib import Path; from app.investigator.preparation_worker import watchParent; import sys; watchParent(Path(sys.argv[1]), timeout=float(sys.argv[2]), lifetime=float(sys.argv[3]))"
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path), str(timeout), str(lifetime)],
        env={**os.environ, "PYTHONPATH": str(backend)}, capture_output=True, timeout=5)
    assert result.returncode == 2


def test_repeated_restart_keeps_the_orphan_worker_recovery_window(api):
    from app.investigator.preparation import ContextPreparer, PreparationBusy
    from app.investigator.schemas import ContextPreparation, ContextPreparationRequest
    client, service, root = api
    id = "b" * 32
    directory = root / "preparations" / id
    directory.mkdir(parents=True)
    (directory / "heartbeat").touch()
    job = ContextPreparation(id=id, status="running", stage="training", createdAt=time.time())
    with service.store.transaction() as db:
        db.execute("INSERT INTO context_preparations VALUES(?,?,?,?,?,?)", (id, "local", "prepare-orphan", job.status, job.model_dump_json(), job.createdAt))
    first = ContextPreparer(root, service.store)
    second = ContextPreparer(root, service.store)
    try:
        assert second.get("local", id).status == "interrupted"
        with pytest.raises(PreparationBusy, match="previous preparation worker"):
            second.start("local", ContextPreparationRequest(requestId="prepare-after-restarts"))
    finally:
        first.close()
        second.close()
