"""Offline regressions for the provider proposal contract, built from captured live replies."""
import json
from pathlib import Path

import pytest

from app.assistant.transport import strict_schema
from app.config import Settings
from app.data.synthetic import SYNTHETIC_SENSORS
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.faults.scenarios import FaultCase
from app.investigator.controller import InvestigationDecision, controllerStatus
from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion
from app.investigator.proposals import ProviderProposal
from test_compound_faults import fitted as fitted  # noqa: F401
from test_nemotron_controller import provider, run, stop

LR = "logistic_regression/lr-probe"
CAPTURED = json.loads((Path(__file__).parent / "fixtures/nemotron-captured-replies.json").read_text(encoding="utf-8"))


def fault(kind="dropout", channel="channel-1", onset=40, length=None, seed=None, **drift):
    component = {"kind": kind, "sensor": channel,
        "onset": {"mode": "seeded", "seed": seed} if seed is not None else {"mode": "explicit", "onset_before_failure": onset},
        "duration": {"mode": "transient", "length": length} if length else {"mode": "persistent"}}
    return {**component, **drift}


def decision(*components, basedOn=()):
    return {"proposal": {"scenario": {"components": list(components)}, "reason": "Test this case.",
        "hypothesis": {"suspected": "It costs warnings.", "supportIf": "Detection falls.", "weakenIf": "Detection holds.", "basedOn": list(basedOn)}},
        "stopReason": None}


@pytest.fixture
def profiled(fitted, tmp_path):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_experiments=6, max_failures=3))
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    config = Settings(mode="full", assistant_provider="nebius", assistant_model="nvidia/nemotron-3-super-120b-a12b",
        nebius_api_key="mock", nebius_reasoning_tokens=0, assistant_live_enabled=True)
    return engine, store, investigation, config


def calls(store, investigation):
    return controllerStatus(store, investigation)["calls"]


def test_every_captured_live_reply_is_rejected_with_feedback_and_never_scored(profiled, monkeypatch):
    engine, store, investigation, config = profiled
    replies = [*CAPTURED["v3"], *CAPTURED["v4"]]
    sent = provider(monkeypatch, [*replies, stop()])
    report = run(store, engine, config, investigation, maxCalls=len(replies) + 1, maxCompletionTokens=100000)
    saved = calls(store, investigation)
    assert report["stopReason"] == "model_stopped" and report["experimentsUsed"] == 0
    assert [call["error"] for call in saved[:-1]] == ["invalid_proposal"] * len(replies)
    assert all(call["feedback"] and len(call["feedback"]) <= 300 for call in saved[:-1])
    assert sent[1]["recentCalls"][-1]["feedback"] == saved[0]["feedback"]
    assert store.load(investigation).proposals == [] and recordFindings(store, investigation) == []


@pytest.mark.parametrize("component,message", [
    ({**fault("drift", length=None), "duration": {"mode": "transient"}, "severity_sd": 1.5, "sign": 1, "ramp_cycles": 10}, "length"),
    ({**fault(), "onset": {"mode": "explicit", "onset_before_failure": 30, "seed": 101}}, "seed"),
    ({**fault(), "severity_sd": 1.0, "sign": 0, "ramp_cycles": 5}, "severity_sd"),
    ({**fault("drift"), "severity_sd": 1.5, "sign": 0, "ramp_cycles": 10}, "sign"),
    ({**fault("drift"), "severity_sd": 1.5, "sign": 1}, "ramp_cycles"),
    ({**fault(), "duration": {"mode": "persistent", "length": 30}}, "length"),
])
def test_the_provider_schema_cannot_express_invalid_parameter_combinations(component, message):
    with pytest.raises(ValueError, match=message):
        ProviderProposal.model_validate_json(json.dumps(decision(component)["proposal"]), strict=True)


def test_valid_alternatives_convert_to_the_existing_domain_model():
    proposal = ProviderProposal.model_validate_json(json.dumps(decision(
        fault("drift", "temp_bearing", onset=30, length=20, severity_sd=2.0, sign=-1, ramp_cycles=10),
        fault("stuck", "vibration_rms", seed=0))["proposal"]), strict=True).toProposal()
    drift, stuck = sorted(proposal.scenario.components, key=lambda atom: atom.kind.value)
    assert (drift.duration.value, drift.length, drift.onset_before_failure, drift.seed, drift.sign) == ("transient", 20, 30, None, -1)
    assert (stuck.duration.value, stuck.length, stuck.onset_before_failure, stuck.seed, stuck.severity_sd) == ("persistent", None, None, 0, None)
    assert proposal.hypothesis.weakenIf == "Detection holds."


def test_schema_uses_only_constructs_the_endpoint_already_accepted():
    text = json.dumps(strict_schema(InvestigationDecision))
    for unsupported in ('"const"', '"oneOf"', '"discriminator"', '"allOf"'):
        assert unsupported not in text
    assert '"anyOf"' in text and '"$ref"' in text and '"enum"' in text


def test_unsupported_groups_and_impossible_timing_get_precise_feedback(profiled, monkeypatch):
    engine, store, investigation, config = profiled
    crossGroup = decision(fault("dropout", "channel-1"), fault("dropout", "channel-4"))
    tooEarly = decision(fault("drift", "channel-1", onset=100, severity_sd=1.5, sign=1, ramp_cycles=30))
    provider(monkeypatch, [crossGroup, tooEarly, stop()])
    run(store, engine, config, investigation, maxCalls=3)
    saved = calls(store, investigation)
    assert "outside the declared groups" in saved[0]["feedback"]
    assert "No development history can apply this case (22 checked)" in saved[1]["feedback"]
    assert "channel-1: history never reaches 100 cycles before failure" in saved[1]["feedback"]
    assert not any(sensor in json.dumps(saved) for sensor in SYNTHETIC_SENSORS)
    assert store.load(investigation).slots_used == 0


def test_partial_coverage_is_allowed_and_the_evaluator_stays_authoritative(profiled, monkeypatch):
    engine, store, investigation, config = profiled
    timing = engine.timing()
    partial = next(row for row in timing["onsetCoverage"] if 0 < row["histories"] < timing["histories"])
    sent = provider(monkeypatch, [decision(fault("dropout", "channel-2", onset=partial["onset"])), stop()])
    run(store, engine, config, investigation, maxCalls=2)
    assert sent[0]["timing"]["maxReachableOnset"] == timing["maxReachableOnset"] == sent[0]["bounds"]["maxOnset"]
    attempt = store.load(investigation).attempts[0]
    result = store.result(attempt.id)
    assert result.status == "partial" and result.evaluated_histories == partial["histories"]
    finding = recordFindings(store, investigation)[0]
    assert finding.status == "inconclusive" and not finding.is_discovery


@pytest.mark.parametrize("case", [
    [{"sensor": "vibration_rms", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60},
        {"sensor": "oil_particles", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60}],
    [{"sensor": "temp_bearing", "kind": "dropout", "duration": "transient", "length": 3, "onset_before_failure": 6}],
    [{"sensor": "pressure_out", "kind": "drift", "duration": "persistent", "onset_before_failure": 95, "severity_sd": 2.0, "sign": 1, "ramp_cycles": 10}],
    [{"sensor": "current_draw", "kind": "stuck", "duration": "persistent", "seed": 7}],
])
def test_preview_agrees_with_evaluated_coverage(profiled, case):
    engine = profiled[0]
    scenario = FaultCase.model_validate({"components": case})
    preview = engine.preview(scenario)
    assert preview["applicable"] == engine.evaluate(scenario).evaluated_histories


def test_correction_calls_use_the_saved_allowance_across_restarts(profiled, monkeypatch):
    engine, store, investigation, config = profiled
    import httpx
    tooEarly = decision(fault("dropout", "channel-1", onset=300))
    provider(monkeypatch, [tooEarly, httpx.ConnectError("network down")])
    assert run(store, engine, config, investigation, maxCalls=3)["stopReason"] == "provider_error"
    assert [call["error"] for call in calls(store, investigation)] == ["invalid_proposal", "provider_error"]
    provider(monkeypatch, [decision(fault("dropout", "channel-1", onset=40))])
    report = run(store, engine, config, investigation, maxCalls=3)
    assert report["stopReason"] == "call_limit" and report["callsUsed"] == 3 and report["experimentsUsed"] == 1
