import sqlite3
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import routes_investigations
from app.config import Settings, reset_settings
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.faults.replay import export_evaluation
from app.faults.scenarios import FaultCase
from app.investigator.service import InvestigationService
from test_compound_faults import component, fitted as fitted  # noqa: F401
from test_nemotron_controller import provider, proposal, stop

LR = "logistic_regression/lr-probe"
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]}
HEADERS = {"x-owner": "alice"}


class Consent:
    def __init__(self):
        self.allowed = True

    def workspace_consent(self):
        return self.allowed


@pytest.fixture
def api(fitted, local_settings, monkeypatch):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    root = local_settings / "investigations"
    export_evaluation(engine, engine.evaluate(FaultCase.model_validate(STUCK_PAIR)), root / "contexts" / "synthetic")
    settings = Settings(mode="full", assistant_provider="nebius", assistant_model="nvidia/nemotron-3-super-120b-a12b",
        nebius_api_key="mock", nebius_reasoning_tokens=0, assistant_live_enabled=True)
    app = FastAPI()
    app.state.investigations = InvestigationService(root, settings)
    app.state.assistant = Consent()
    app.include_router(routes_investigations.router)
    monkeypatch.setattr(routes_investigations, "library_owner", lambda request: request.headers.get("x-owner", "local"))
    yield TestClient(app), app.state.investigations, root
    app.state.investigations.close()


def create(client, **changes):
    body = {"context": "synthetic", "criterion": {"candidate": LR}, "proposals": [STUCK_PAIR], "seed": 2, **changes}
    response = client.post("/api/investigations", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def started(service, investigation):
    with service.store.connection() as db:
        return db.execute("SELECT COUNT(*) FROM investigation_events WHERE investigation=? AND kind LIKE 'started:%'", (investigation,)).fetchone()[0]


def test_contexts_come_only_from_the_server_registry(api):
    client, service, root = api
    contexts = client.get("/api/investigations/contexts").json()
    assert [item["name"] for item in contexts] == ["synthetic"]
    assert contexts[0]["profile"] == "synthetic-rotating-v1" and contexts[0]["clean"][LR]["histories"] == 22
    assert client.post("/api/investigations", json={"context": "missing"}, headers=HEADERS).status_code == 404
    assert client.post("/api/investigations", json={"context": "../synthetic"}, headers=HEADERS).status_code == 422


def test_full_lifecycle_runs_in_the_background_and_is_owned(api):
    client, service, root = api
    investigation = create(client)
    assert [item["id"] for item in client.get("/api/investigations", headers=HEADERS).json()] == [investigation]
    assert client.get("/api/investigations", headers={"x-owner": "bob"}).json() == []
    for method, path in [("get", ""), ("post", "/start"), ("post", "/cancel"), ("get", "/export")]:
        kwargs = {"json": {"requestId": "bob-request-1"}} if path == "/start" else {}
        assert getattr(client, method)(f"/api/investigations/{investigation}{path}", headers={"x-owner": "bob"}, **kwargs).status_code == 404

    response = client.post(f"/api/investigations/{investigation}/start", json={"requestId": "start-request-1"}, headers=HEADERS)
    assert response.status_code == 200
    service.wait(investigation)
    view = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()
    assert [event["kind"] for event in view["events"]] == ["created", "started:run", "finished:run"]
    assert view["events"][-1]["detail"] == "completed" and view["active"] is None
    assert view["experimentsUsed"] == 3 and view["discoveries"] == 1
    assert view["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"]

    retry = client.post(f"/api/investigations/{investigation}/start", json={"requestId": "start-request-1"}, headers=HEADERS)
    assert retry.status_code == 200 and started(service, investigation) == 1
    service.wait(investigation)
    assert client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()["experimentsUsed"] == 3

    attempt = next(item["attempt_id"] for item in view["findings"] if item["status"] == "measured_failure")
    replay = client.post(f"/api/investigations/{investigation}/results/{attempt}/replay", headers=HEADERS).json()
    assert replay["matches"] is True and replay["attempt"] == attempt
    assert client.post(f"/api/investigations/{investigation}/results/missing/replay", headers=HEADERS).status_code == 404

    client.post(f"/api/investigations/{investigation}/reduce", json={"requestId": "reduce-request-1", "attempt": attempt, "maxExperiments": 20}, headers=HEADERS)
    service.wait(investigation)
    client.post(f"/api/investigations/{investigation}/remedies", json={"requestId": "remedy-request-1", "kind": "threshold", "threshold": .5}, headers=HEADERS)
    service.wait(investigation)
    view = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()
    assert view["reductions"][0]["status"] == "complete" and view["remedies"][0]["improved"] >= 1
    assert [event["kind"] for event in view["events"]][-4:] == ["started:reduce", "finished:reduce", "started:remedy", "finished:remedy"]
    assert client.get(f"/api/investigations/{investigation}/export", headers=HEADERS).json()["id"] == investigation
    denied = client.post(f"/api/investigations/{investigation}/remedies", json={"requestId": "remedy-request-2", "kind": "augmented"}, headers=HEADERS)
    assert denied.status_code == 403


def test_only_one_operation_runs_and_cancel_resume_work(api, monkeypatch):
    client, service, root = api
    investigation = create(client)
    release = threading.Event()
    from app.faults import investigation as runnerModule
    original = runnerModule.ExperimentRunner.run
    def slow(self, *args, **kwargs):
        release.wait(10)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(runnerModule.ExperimentRunner, "run", slow)
    assert client.post(f"/api/investigations/{investigation}/start", json={"requestId": "first-request"}, headers=HEADERS).json()["active"] == "run"
    assert client.post(f"/api/investigations/{investigation}/start", json={"requestId": "second-request"}, headers=HEADERS).status_code == 409
    assert client.post(f"/api/investigations/{investigation}/resume", headers=HEADERS).status_code == 409
    assert client.post(f"/api/investigations/{investigation}/cancel", headers=HEADERS).json()["state"]["cancel_requested"] is True
    release.set()
    service.wait(investigation)
    view = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()
    assert view["events"][-1]["kind"] == "finished:run" and view["events"][-1]["detail"] == "cancelled" and view["experimentsUsed"] == 0
    assert client.post(f"/api/investigations/{investigation}/resume", headers=HEADERS).json()["state"]["cancel_requested"] is False
    client.post(f"/api/investigations/{investigation}/start", json={"requestId": "third-request"}, headers=HEADERS)
    service.wait(investigation)
    assert client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()["experimentsUsed"] == 3


def test_agent_runs_need_permission_and_stop_when_it_is_revoked(api, monkeypatch):
    client, service, root = api
    investigation = create(client, proposals=[], seed=0)
    path = f"/api/investigations/{investigation}/start"
    assert client.post(path, json={"requestId": "agent-request-1", "mode": "agent"}, headers=HEADERS).status_code == 403
    client.app.state.assistant.allowed = False
    assert client.post(path, json={"requestId": "agent-request-2", "mode": "agent", "allowProvider": True}, headers=HEADERS).status_code == 403
    client.app.state.assistant.allowed = True
    calls = provider(monkeypatch, [proposal(), stop()])
    client.post(path, json={"requestId": "agent-request-3", "mode": "agent", "allowProvider": True, "maxProviderCalls": 2}, headers=HEADERS)
    service.wait(investigation)
    view = client.get(f"/api/investigations/{investigation}", headers=HEADERS).json()
    assert len(calls) == 2 and view["events"][-1] == {**view["events"][-1], "kind": "finished:agent", "detail": "model_stopped"}
    assert view["controller"]["callsUsed"] == 2 and view["experimentsUsed"] == 1

    second = create(client, proposals=[], seed=0)
    def revokeWhileThinking(packet, count):
        client.app.state.assistant.allowed = False
        return proposal("channel-2")
    provider(monkeypatch, revokeWhileThinking)
    client.app.state.assistant.allowed = True
    client.post(f"/api/investigations/{second}/start", json={"requestId": "agent-request-4", "mode": "agent", "allowProvider": True}, headers=HEADERS)
    service.wait(second)
    view = client.get(f"/api/investigations/{second}", headers=HEADERS).json()
    assert view["events"][-1]["detail"] == "cancelled" and view["state"]["proposals"] == [] and view["experimentsUsed"] == 0


def test_restart_marks_unfinished_work_interrupted(api):
    client, service, root = api
    investigation = create(client)
    with sqlite3.connect(service.store.path) as db:
        db.execute("INSERT INTO investigation_events(investigation,kind,request_id,created) VALUES(?,?,?,0)", (investigation, "started:run", "lost-request"))
    restarted = InvestigationService(root, service.settings)
    assert [event.kind for event in restarted.view("alice", investigation).events][-1] == "interrupted"
    assert [event.kind for event in InvestigationService(root, service.settings).view("alice", investigation).events].count("interrupted") == 1


def test_routes_are_local_only_and_check_origin(api, monkeypatch):
    client, service, root = api
    assert client.post("/api/investigations", json={"context": "synthetic"}, headers={**HEADERS, "origin": "https://elsewhere.example"}).status_code == 403
    monkeypatch.setenv("SIDEKICK_MODE", "replay")
    reset_settings()
    assert client.get("/api/investigations", headers=HEADERS).status_code == 403
