import asyncio
import json
from types import SimpleNamespace

import httpx
from openai import AsyncOpenAI
import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.investigator.records import InvestigationBudget, InvestigationStore
from test_investigation_records import engine as engine


def makeProposal(**changes):
    scenario = {"components": [
        {"sensor": "temp_bearing", "kind": "dropout", "duration": "persistent", "onset_before_failure": 40},
        {"sensor": "vibration_rms", "kind": "drift", "duration": "persistent", "onset_before_failure": 40,
            "severity_sd": 1.5, "sign": 1, "ramp_cycles": 10}]}
    return {"reason": "Check whether losing temperature readings masks vibration drift.", "scenario": scenario, **changes}


@pytest.fixture
def record(tmp_path, engine):
    return InvestigationStore(tmp_path).create(engine, objective="Find warning failures.",
        budget=InvestigationBudget(max_experiments=3, max_proposals=6, max_seconds=120))


def test_valid_proposal_is_typed_immutable_and_does_not_execute(record, engine, monkeypatch, tmp_path):
    from app.investigator.proposals import ScenarioProposal, validateProposal
    monkeypatch.setattr(engine, "evaluate", lambda *_a, **_k: pytest.fail("Validation executed an experiment"))
    before = InvestigationStore(tmp_path).path.read_bytes()
    proposal = validateProposal(json.dumps(makeProposal(reason="  Test combined faults.  ")), record, engine)
    assert isinstance(proposal, ScenarioProposal)
    assert proposal.reason == "Test combined faults."
    assert proposal.scenario.scenario_id.startswith("compound-v1-")
    assert len(proposal.scenario.components) == 2
    assert InvestigationStore(tmp_path).get(record.id) == record
    assert InvestigationStore(tmp_path).path.read_bytes() == before
    with pytest.raises(ValueError):
        proposal.reason = "Changed"
    with pytest.raises(ValueError):
        proposal.scenario.components[0].sensor = "other"


def test_component_order_does_not_change_the_scenario(record, engine):
    from app.investigator.proposals import validateProposal
    payload = makeProposal()
    first = validateProposal(json.dumps(payload), record, engine)
    payload["scenario"]["components"].reverse()
    second = validateProposal(json.dumps(payload), record, engine)
    assert first.scenario == second.scenario
    assert first.scenario.scenario_id == second.scenario.scenario_id


def test_single_fault_supports_an_explicit_zero_seed(record, engine):
    from app.investigator.proposals import validateProposal
    payload = makeProposal()
    payload["scenario"]["components"] = [payload["scenario"]["components"][0]]
    payload["scenario"]["components"][0].update(onset_before_failure=None, seed=0)
    proposal = validateProposal(json.dumps(payload), record, engine)
    assert proposal.scenario.scenario_id.startswith("single-v1-")
    assert proposal.scenario.components[0].seed == 0
    assert proposal.scenario.components[0].onset_before_failure is None


@pytest.mark.parametrize("reason", ["", " \n\t", "x" * 1601, 42, None])
def test_invalid_reasons_are_rejected(record, engine, reason):
    from app.investigator.proposals import validateProposal
    with pytest.raises(ValueError):
        validateProposal(json.dumps(makeProposal(reason=reason)), record, engine)


@pytest.mark.parametrize("payload", ["not json", "null", "[]", "{}", None, {}, b"{}"])
def test_invalid_payloads_are_rejected(record, engine, payload):
    from app.investigator.proposals import validateProposal
    with pytest.raises(ValueError):
        validateProposal(payload, record, engine)


@pytest.mark.parametrize("field", ["context_fingerprint", "thresholds", "policy", "budget", "result", "command"])
def test_provider_cannot_supply_server_fields(record, engine, field):
    from app.investigator.proposals import validateProposal
    with pytest.raises(ValueError):
        validateProposal(json.dumps(makeProposal(**{field: "untrusted"})), record, engine)


@pytest.mark.parametrize("changes", [{"sensor": "unknown"}, {"onset_before_failure": 1}, {"onset_before_failure": 501},
    {"onset_before_failure": True}, {"onset_before_failure": "40"}, {"onset_before_failure": None},
    {"duration": "transient", "length": 121}, {"kind": "drift", "severity_sd": 4, "sign": 1, "ramp_cycles": 10},
    {"kind": "drift", "severity_sd": "1.5", "sign": 1, "ramp_cycles": 10},
    {"kind": "drift", "severity_sd": float("nan"), "sign": 1, "ramp_cycles": 10},
    {"kind": "drift", "severity_sd": 1.5, "sign": 1, "ramp_cycles": 121}, {"command": "untrusted"}])
def test_invalid_or_out_of_policy_components_are_rejected(record, engine, changes):
    from app.investigator.proposals import validateProposal
    payload = makeProposal()
    payload["scenario"]["components"][0].update(changes)
    with pytest.raises(ValueError):
        validateProposal(json.dumps(payload), record, engine)


def test_same_sensor_components_are_rejected(record, engine):
    from app.investigator.proposals import validateProposal
    payload = makeProposal()
    payload["scenario"]["components"][1]["sensor"] = "temp_bearing"
    with pytest.raises(ValueError):
        validateProposal(json.dumps(payload), record, engine)


@pytest.mark.parametrize("limits", [{"max_components": 1}, {"allowed_groups": (("temp_bearing",), ("vibration_rms",))}])
def test_investigation_specific_policy_is_used(tmp_path, engine, limits):
    from app.investigator.proposals import validateProposal
    policy = engine.policy.model_copy(update=limits)
    restricted = FixedDevelopmentEvaluator(engine._training, engine.thresholds, policy)
    record = InvestigationStore(tmp_path).create(restricted, objective="Test restricted faults.",
        budget=InvestigationBudget(max_experiments=3, max_proposals=6, max_seconds=120))
    with pytest.raises(ValueError):
        validateProposal(json.dumps(makeProposal()), record, restricted)


def test_mismatched_context_cannot_validate_a_proposal(record, engine):
    from app.investigator.proposals import validateProposal
    other = FixedDevelopmentEvaluator(engine._training, {"age_baseline/record-probe": 61.0}, engine.policy)
    with pytest.raises(ValueError, match="context"):
        validateProposal(json.dumps(makeProposal()), record, other)


def test_unchecked_record_changes_are_revalidated(record, engine):
    from app.investigator.proposals import validateProposal
    budget = record.budget.model_copy(update={"max_experiments": 0})
    changed = record.model_copy(update={"budget": budget})
    with pytest.raises(ValueError):
        validateProposal(json.dumps(makeProposal()), changed, engine)


def test_json_size_limit_is_checked_before_parsing(record, engine):
    from app.investigator.proposals import MAX_PROPOSAL_BYTES, validateProposal
    payload = json.dumps(makeProposal(reason="Inspect temperature drift: é."), ensure_ascii=False)
    padded = payload + " " * (MAX_PROPOSAL_BYTES - len(payload.encode("utf-8")))
    assert validateProposal(padded, record, engine).reason.endswith("é.")
    with pytest.raises(ValueError, match="size"):
        validateProposal(padded + " ", record, engine)


def test_nebius_transport_accepts_the_proposal_contract_offline(record, engine):
    from app.assistant.transport import request_structured
    from app.investigator.proposals import ScenarioProposal, validateProposal
    calls = []
    response = ScenarioProposal.model_validate_json(json.dumps(makeProposal()), strict=True).model_dump_json()

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert set(schema["schema"]["required"]) == {"reason", "scenario", "hypothesis"}
        assert schema["schema"]["additionalProperties"] is False
        return httpx.Response(200, json={"id": "proposal-test", "object": "chat.completion", "created": 0, "model": "fixture",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": response}}]})

    async def run():
        settings = SimpleNamespace(assistant_provider="nebius", assistant_model="fixture")
        async with AsyncOpenAI(api_key="mock", max_retries=0, base_url="http://fixture.invalid/v1/",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            proposal = await request_structured(client, settings, history=[{"role": "user", "content": "Synthetic proposal check"}],
                response_model=ScenarioProposal, max_output_tokens=512)
            return validateProposal(proposal.model_dump_json(), record, engine)

    assert asyncio.run(run()).scenario.scenario_id.startswith("compound-v1-")
    assert len(calls) == 1
