"""Injected failures must never change recorded evidence or reset paid-work limits."""
import asyncio
import json
import sqlite3

import httpx
from openai import AsyncOpenAI
import pytest

from app.faults.investigation import ExperimentRunner, LeaseLost
from app.investigator.controller import ControllerLimits, InvestigationDecision, NemotronController, controllerStatus
from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion
from test_compound_faults import fitted as fitted  # noqa: F401
from test_nemotron_controller import proposal, setup

LR = "logistic_regression/lr-probe"


def scripted(monkeypatch, replies):
    from app.investigator import controller
    def respond(request):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content, finish = reply if isinstance(reply, tuple) else (InvestigationDecision.model_validate_json(json.dumps(reply)).model_dump_json(), "stop")
        return httpx.Response(200, json={"id": "fi", "object": "chat.completion", "created": 0, "model": "fixture",
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    def client(**options):
        options["base_url"] = "http://fixture.invalid/v1/"
        return AsyncOpenAI(**options, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(controller, "AsyncOpenAI", client)


def agent(store, fixed, config, investigation):
    controller = NemotronController(store, fixed, config, ControllerLimits(maxCalls=12, maxCompletionTokens=200000))
    return asyncio.run(controller.run(investigation, allowProvider=True))


def evidence(store, investigation):
    with sqlite3.connect(store.path) as db:
        return db.execute("SELECT id, result_digest FROM attempts WHERE investigation=? AND status='completed' ORDER BY reserved", (investigation,)).fetchall()


def test_failures_preserve_evidence_and_never_reset_counters(fitted, tmp_path, monkeypatch):
    fixed, store, investigation, config = setup(fitted, tmp_path, experiments=6)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    calls = []

    def checkpoint():
        status = controllerStatus(store, investigation)
        calls.append((status["callsUsed"], status["reservedCompletionTokens"]))
        assert calls == sorted(calls)
        return status

    scripted(monkeypatch, [proposal(), httpx.ConnectError("network down")])
    agent(store, fixed, config, investigation)
    baseline = evidence(store, investigation)
    findings = {item.attempt_id: item for item in recordFindings(store, investigation)}
    assert len(baseline) == 1
    checkpoint()

    def unchanged():
        assert evidence(store, investigation)[:1] == baseline
        assert {item.attempt_id: item for item in recordFindings(store, investigation)}[baseline[0][0]] == findings[baseline[0][0]]

    def steady():
        unchanged()
        checkpoint()

    scripted(monkeypatch, [('{"proposal": null, "stopReason": "cut', "length")])
    assert agent(store, fixed, config, investigation)["stopReason"] == "invalid_response"
    steady()

    scripted(monkeypatch, [("not json", "stop")])
    assert agent(store, fixed, config, investigation)["stopReason"] == "invalid_response"
    steady()

    scripted(monkeypatch, [httpx.ConnectError("network down")])
    assert agent(store, fixed, config, investigation)["stopReason"] == "provider_error"
    steady()

    scripted(monkeypatch, [proposal("channel-99"), httpx.ConnectError("network down")])
    agent(store, fixed, config, investigation)
    assert controllerStatus(store, investigation)["calls"][-2]["error"] == "invalid_proposal"
    steady()

    original = NemotronController.requestDecision
    async def stealLease(self, text, limits, meta):
        with store.transaction() as db:
            db.execute("UPDATE investigation_runs SET lease_token='other', lease_expires=9e12 WHERE id=?", (investigation,))
        return InvestigationDecision.model_validate_json(json.dumps(proposal("channel-2")))
    monkeypatch.setattr(NemotronController, "requestDecision", stealLease)
    with pytest.raises(LeaseLost):
        agent(store, fixed, config, investigation)
    monkeypatch.setattr(NemotronController, "requestDecision", original)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE investigation_runs SET lease_token=NULL, lease_expires=NULL WHERE id=?", (investigation,))
    steady()

    store.add_proposals(investigation, [{"components": [{"sensor": "vibration_rms", "kind": "stuck", "duration": "persistent", "onset_before_failure": 30}]}])
    with monkeypatch.context() as crashing:
        crashing.setattr(fixed, "evaluate", lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            ExperimentRunner(store, fixed).run(investigation)
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert len(summary.interrupted_recovered) == 1
    steady()

    state = store.load(investigation)
    assert state.slots_used <= state.budget.max_experiments
    assert calls[-1][0] == len(controllerStatus(store, investigation)["calls"])
