import asyncio
import json
import sqlite3

import httpx
from openai import AsyncOpenAI
import pytest

from app.config import Settings
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationBusy, InvestigationStore
from test_compound_faults import evaluator, fitted as fitted


def proposal(sensor="channel-1", **changes):
    component = {"sensor": sensor, "kind": "dropout", "duration": "persistent", "onset_before_failure": 40, **changes}
    return {"proposal": {"scenario": {"components": [component]}, "reason": "Inspect loss of this channel."}, "stopReason": None}


def stop():
    return {"proposal": None, "stopReason": "Enough evidence for the next engineering review."}


def setup(fitted, tmp_path, *, experiments=4, runSeconds=600, **settings):
    fixed = evaluator(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget(max_experiments=experiments, max_failures=min(2, experiments), max_run_seconds=runSeconds))
    config = Settings(mode="full", assistant_provider="nebius", assistant_model="nvidia/nemotron-3-super-120b-a12b",
        nebius_api_key="mock", nebius_reasoning_tokens=0, **settings)
    return fixed, store, investigation, config


def provider(monkeypatch, replies):
    from app.investigator import controller
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        packet = json.loads(payload["messages"][-1]["content"])
        calls.append(packet)
        reply = replies(packet, len(calls)) if callable(replies) else replies[len(calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else controller.InvestigationDecision.model_validate_json(json.dumps(reply)).model_dump_json()
        return httpx.Response(200, json={"id": "controller-test", "object": "chat.completion", "created": 0, "model": "fixture",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})

    def client(**options):
        assert options["max_retries"] == 0
        options["base_url"] = "http://fixture.invalid/v1/"
        return AsyncOpenAI(**options, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(controller, "AsyncOpenAI", client)
    return calls


def run(store, fixed, config, investigation, **limits):
    from app.investigator.controller import ControllerLimits, NemotronController
    controller = NemotronController(store, fixed, config, ControllerLimits(**limits))
    return asyncio.run(controller.run(investigation, allowProvider=True))


def test_model_observes_previous_result_before_choosing_the_next_case(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)

    def decide(packet, count):
        if count == 1:
            assert packet["experiments"] == []
            return proposal()
        assert packet["experiments"][0]["models"]
        assert packet["experiments"][0]["evaluatedHistories"] == 22
        return proposal("channel-2") if count == 2 else stop()

    calls = provider(monkeypatch, decide)
    report = run(store, fixed, config, investigation)
    assert len(calls) == report["callsUsed"] == 3
    assert report["stopReason"] == "model_stopped" and report["experimentsUsed"] == 2
    assert len(report["results"]) == 2
    assert {atom.sensor for item in store.load(investigation).attempts for atom in store.result(item.id).scenario.components} == {"temp_bearing", "vibration_rms"}
    packet = json.dumps(calls)
    for private in ["temp_bearing", "vibration_rms", "logistic_regression/lr-probe", "data_hash", "equipment_id", "mock"]:
        assert private not in packet


def test_local_policy_rejection_counts_a_call_without_using_an_experiment(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [proposal("unknown"), proposal(), stop()])
    report = run(store, fixed, config, investigation)
    assert report["callsUsed"] == 3 and report["experimentsUsed"] == 1
    assert calls[1]["recentCalls"][0]["status"] == "rejected"
    assert len(store.load(investigation).proposals) == 1


def test_duplicates_do_not_consume_extra_experiments(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    provider(monkeypatch, [proposal(), proposal(), stop()])
    report = run(store, fixed, config, investigation)
    assert report["experimentsUsed"] == 1 and report["callsUsed"] == 3
    assert [item.status for item in store.load(investigation).proposals] == ["completed", "duplicate"]


def test_call_limits_and_model_stop_survive_restart(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [proposal(), proposal("channel-2")])
    first = run(store, fixed, config, investigation, maxCalls=2)
    second = run(InvestigationStore(tmp_path / "store"), fixed, config, investigation, maxCalls=2)
    assert first["stopReason"] == second["stopReason"] == "call_limit"
    assert first["reservedCompletionTokens"] == second["reservedCompletionTokens"]
    assert len(calls) == 2
    with pytest.raises(ValueError, match="configuration"):
        run(store, fixed, config, investigation, maxCalls=3)


def test_completion_budget_is_reserved_before_dispatch(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)

    def decide(packet, count):
        with sqlite3.connect(store.path) as db:
            assert db.execute("SELECT status,reserved_tokens FROM controller_calls").fetchall() == [("pending", 512)]
        return proposal()

    calls = provider(monkeypatch, decide)
    report = run(store, fixed, config, investigation, maxCalls=4, maxOutputTokens=512, maxCompletionTokens=700)
    assert len(calls) == 1 and report["stopReason"] == "token_limit"
    assert report["reservedCompletionTokens"] == 512


@pytest.mark.parametrize("reply,reason", [("not json", "invalid_response"), (httpx.ConnectError("private provider detail"), "provider_error")])
def test_provider_failures_consume_the_reservation_and_do_not_retry(fitted, tmp_path, monkeypatch, reply, reason):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [reply])
    report = run(store, fixed, config, investigation)
    assert len(calls) == report["callsUsed"] == 1
    assert report["stopReason"] == reason and report["experimentsUsed"] == 0
    assert "private provider detail" not in json.dumps(report)


def test_provider_permission_is_explicit_and_cancellation_uses_no_call(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [])
    controller = NemotronController(store, fixed, config)
    with pytest.raises(PermissionError):
        asyncio.run(controller.run(investigation))
    store.request_cancel(investigation)
    report = asyncio.run(controller.run(investigation, allowProvider=True))
    assert report["stopReason"] == "cancelled" and report["callsUsed"] == 0 and calls == []


def test_experiment_limit_stops_before_another_paid_call(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path, experiments=1)
    calls = provider(monkeypatch, [proposal()])
    report = run(store, fixed, config, investigation)
    assert report["stopReason"] == "experiment_limit" and len(calls) == 1


def test_manual_runner_is_blocked_while_the_provider_is_thinking(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)

    def decide(packet, count):
        with pytest.raises(InvestigationBusy):
            ExperimentRunner(store, fixed).run(investigation)
        return stop()

    provider(monkeypatch, decide)
    report = run(store, fixed, config, investigation)
    assert report["stopReason"] == "model_stopped"


def test_oversized_inputs_stop_before_dispatch(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [])
    report = run(store, fixed, config, investigation, maxInputBytes=256)
    assert report["stopReason"] == "input_limit" and report["callsUsed"] == 0 and calls == []


def test_model_stop_survives_restart_and_cancel_resume(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [stop()])
    assert run(store, fixed, config, investigation)["stopReason"] == "model_stopped"
    assert run(store, fixed, config, investigation)["stopReason"] == "model_stopped"
    store.request_cancel(investigation)
    assert run(store, fixed, config, investigation)["stopReason"] == "cancelled"
    store.resume(investigation)
    assert run(store, fixed, config, investigation)["stopReason"] == "model_stopped"
    assert len(calls) == 1


def test_cancel_during_provider_request_keeps_its_reservation(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)

    async def waitForCancellation(self, text, limits):
        store.request_cancel(investigation)
        await asyncio.Event().wait()

    monkeypatch.setattr(NemotronController, "requestDecision", waitForCancellation)
    report = run(store, fixed, config, investigation)
    assert report["stopReason"] == "cancelled" and report["callsUsed"] == 1
    assert report["reservedCompletionTokens"] == 1024 and report["experimentsUsed"] == 0
    with store.connection() as db:
        assert db.execute("SELECT status FROM controller_calls").fetchall() == [("cancelled",)]


def test_async_interruption_records_the_call_and_releases_the_lease(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)
    entered = asyncio.Event()

    async def wait(self, text, limits):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(NemotronController, "requestDecision", wait)

    async def interrupt():
        controller = NemotronController(store, fixed, config)
        task = asyncio.create_task(controller.run(investigation, allowProvider=True))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(interrupt())
    with store.connection() as db:
        assert db.execute("SELECT status FROM controller_calls").fetchall() == [("interrupted",)]
        assert db.execute("SELECT lease_token FROM investigation_runs").fetchone() == (None,)


def test_request_timeout_is_bounded_and_does_not_retry(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path, assistant_timeout_seconds=.02)

    async def wait(self, text, limits):
        await asyncio.Event().wait()

    monkeypatch.setattr(NemotronController, "requestDecision", wait)
    report = run(store, fixed, config, investigation)
    assert report["stopReason"] == "provider_error" and report["callsUsed"] == 1
    assert report["experimentsUsed"] == 0


def test_a_lost_lease_cannot_publish_the_model_reply(fitted, tmp_path, monkeypatch):
    from app.faults.investigation import LeaseLost
    from app.investigator.controller import InvestigationDecision, NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)

    async def replaceOwner(self, text, limits):
        with store.transaction() as db:
            db.execute("UPDATE investigation_runs SET lease_token='successor',lease_expires=9e12 WHERE id=?", (investigation,))
        return InvestigationDecision.model_validate_json(json.dumps(proposal()))

    monkeypatch.setattr(NemotronController, "requestDecision", replaceOwner)
    with pytest.raises(LeaseLost):
        run(store, fixed, config, investigation)
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM proposals").fetchone() == (0,)
        assert db.execute("SELECT status FROM controller_calls").fetchall() == [("pending",)]
        assert db.execute("SELECT lease_token FROM investigation_runs").fetchone() == ("successor",)


def test_cancel_at_model_stop_does_not_create_a_terminal_stop(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)
    provider(monkeypatch, [stop(), stop()])
    controller = NemotronController(store, fixed, config)
    original = controller.finishCall

    def cancel(*args, **kwargs):
        store.request_cancel(investigation)
        return original(*args, **kwargs)

    monkeypatch.setattr(controller, "finishCall", cancel)
    first = asyncio.run(controller.run(investigation, allowProvider=True))
    assert first["stopReason"] == "cancelled" and first["modelStopReason"] is None
    store.resume(investigation)
    assert run(store, fixed, config, investigation)["stopReason"] == "model_stopped"


def test_a_queued_reply_runs_before_another_provider_call_after_restart(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [proposal(), stop()])
    controller = NemotronController(store, fixed, config)
    original = controller.finishCall

    def interrupt(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Simulated exit after saving the proposal")

    monkeypatch.setattr(controller, "finishCall", interrupt)
    with pytest.raises(RuntimeError):
        asyncio.run(controller.run(investigation, allowProvider=True))
    assert store.load(investigation).slots_used == 0
    report = run(store, fixed, config, investigation)
    assert report["callsUsed"] == len(calls) == 2 and report["experimentsUsed"] == 1
    assert calls[1]["experiments"][0]["evaluatedHistories"] == 22


def test_crashed_pending_call_is_counted_without_repeating_it(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    calls = provider(monkeypatch, [httpx.ConnectError("fixture")])
    run(store, fixed, config, investigation, maxCalls=1)
    with store.transaction() as db:
        db.execute("UPDATE controller_calls SET status='pending',finished=NULL")
        db.execute("UPDATE investigation_runs SET lease_token='dead',lease_expires=0 WHERE id=?", (investigation,))
    report = run(store, fixed, config, investigation, maxCalls=1)
    assert report["callsUsed"] == len(calls) == 1 and report["stopReason"] == "call_limit"
    with store.connection() as db:
        assert db.execute("SELECT status FROM controller_calls").fetchall() == [("interrupted",)]


@pytest.mark.parametrize("field,value", [("mode", "replay"), ("assistant_provider", "openai"),
    ("assistant_model", "other/model"), ("assistant_live_enabled", False), ("nebius_api_key", "")])
def test_invalid_provider_configuration_sends_nothing(fitted, tmp_path, monkeypatch, field, value):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    setattr(config, field, value)
    calls = provider(monkeypatch, [])
    with pytest.raises(ValueError):
        run(store, fixed, config, investigation)
    assert calls == []


def test_reasoning_allowance_is_included_in_each_reservation(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path)
    config.nebius_reasoning_tokens = 4096
    calls = provider(monkeypatch, [stop()])
    report = run(store, fixed, config, investigation, maxOutputTokens=512)
    assert len(calls) == 1 and report["reservedCompletionTokens"] == 4608


def test_cli_requires_permission_before_loading_a_context(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts/run_fault_investigation.py"), "--agent", "unused",
        "--store", str(tmp_path / "unused-store")], cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2 and "--allow-nebius" in result.stderr
    assert not (tmp_path / "unused-store").exists()


def test_controller_deadline_stops_a_waiting_request(fitted, tmp_path, monkeypatch):
    from app.investigator.controller import NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path, runSeconds=.02)

    async def wait(self, text, limits):
        await asyncio.Event().wait()

    monkeypatch.setattr(NemotronController, "requestDecision", wait)
    report = run(store, fixed, config, investigation)
    assert report["stopReason"] == "time_limit" and report["experimentsUsed"] == 0
    assert report["failures"] == 0


def test_a_finished_call_cannot_queue_another_proposal(fitted, tmp_path):
    from app.faults.investigation import LeaseLost
    from app.investigator.controller import ControllerLimits, InvestigationDecision, NemotronController
    fixed, store, investigation, config = setup(fitted, tmp_path)
    controller = NemotronController(store, fixed, config)
    record, limits = store.get(investigation), ControllerLimits()
    with controller.runner.lease(investigation) as token:
        controller.configure(record, limits, 1024, token)
        call, _ = controller.reserveCall(record, limits, 1024, token, "{}")
        checked = controller.decodeProposal(InvestigationDecision.model_validate_json(json.dumps(proposal())).proposal, record)
        controller.finishCall(investigation, token, call, "accepted", proposal=checked)
        with pytest.raises(LeaseLost):
            controller.finishCall(investigation, token, call, "accepted", proposal=checked)
    assert len(store.load(investigation).proposals) == 1


def test_status_is_offline_and_contains_no_credentials(fitted, tmp_path, monkeypatch):
    import subprocess
    import sys
    from pathlib import Path
    fixed, store, investigation, config = setup(fitted, tmp_path)
    provider(monkeypatch, [stop()])
    run(store, fixed, config, investigation)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts/run_fault_investigation.py"), "--store", str(tmp_path / "store"),
        "--status", investigation], cwd=root, capture_output=True, text=True, check=True, timeout=10)
    status = json.loads(result.stdout)["controller"]
    assert status["callsUsed"] == 1 and status["calls"][0]["status"] == "stopped"
    assert status["configuration"]["limits"]["maxCalls"] == 4
    assert "mock" not in result.stdout and "api_key" not in result.stdout


def test_agent_cli_runs_the_controller_with_the_existing_transport(fitted, tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    import dotenv
    import app.config
    from app.faults.replay import export_evaluation
    from app.models.candidates import LogisticRegressionCandidate, AgeBaselineCandidate
    from test_compound_faults import scenario
    fixed, store, investigation, config = setup(fitted, tmp_path)
    package = tmp_path / "context"
    export_evaluation(fixed, fixed.evaluate(scenario()), package)
    calls = provider(monkeypatch, [proposal(), stop()])
    path = Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py"
    spec = importlib.util.spec_from_file_location("fault_investigation_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    def unexpectedFit(*_args, **_kwargs):
        pytest.fail("The controller retrained a model")

    monkeypatch.setattr(LogisticRegressionCandidate, "fit", unexpectedFit)
    monkeypatch.setattr(AgeBaselineCandidate, "fit", unexpectedFit)
    monkeypatch.setattr(app.config, "get_settings", lambda: config)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_args, **_kwargs: None)
    assert cli.main(["--store", str(tmp_path / "store"), "--context", str(package), "--trust-local-artifact",
        "--agent", investigation, "--allow-nebius", "--max-provider-calls", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["callsUsed"] == len(calls) == 2 and report["experimentsUsed"] == 1
    assert report["stopReason"] == "model_stopped"
