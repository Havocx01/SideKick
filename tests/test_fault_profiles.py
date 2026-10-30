import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.data.synthetic import SYNTHETIC_CONSTANT, SYNTHETIC_SENSORS
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy, names
from app.faults.scenarios import FaultCase, FaultPolicy, Profile
from app.investigator.findings import FindingCriterion, classify
from test_compound_faults import component, fitted as fitted  # noqa: F401

PROFILE = "synthetic-rotating-v1"
LR, AGE = "logistic_regression/lr-probe", "age_baseline/age-probe"
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60),
    component("oil_particles", kind="stuck", onset_before_failure=60)]}


def engine(fitted):
    return FixedDevelopmentEvaluator(fitted, {LR: .95, AGE: 60.0}, loadPolicy(PROFILE))


def case(*parts):
    return FaultCase.model_validate({"components": list(parts)})


def test_synthetic_profile_covers_the_fixture_and_labels_its_assumptions():
    policy = loadPolicy(PROFILE)
    assert names() == [PROFILE]
    assert set(policy.allowed_sensors) == set(SYNTHETIC_SENSORS) and not set(policy.allowed_sensors) & set(SYNTHETIC_CONSTANT)
    assert all(any(sensor in group for group in policy.allowed_groups) for sensor in policy.allowed_sensors)
    assert policy.profile.synthetic and policy.assumptions.startswith("Synthetic")
    assert {item.provenance for item in policy.profile.constraints} == {"prototype_assumption"}
    with pytest.raises(ValueError, match="Unknown fault profile"):
        loadPolicy("missing")


@pytest.mark.parametrize("parts,message", [
    ([component("oil_particles", kind="drift", severity_sd=1.0, sign=1, ramp_cycles=5)], "Fault kind"),
    ([component("pressure_out", kind="drift", severity_sd=2.5, sign=1, ramp_cycles=5)], "profile for this sensor"),
    ([component("temp_bearing"), component("pressure_out")], "declared groups"),
    ([component("ambient_temp"), component("vibration_rms")], "declared groups"),
    ([component("rated_voltage")], "allowed mapping"),
])
def test_profile_rejects_invalid_cases_before_any_scoring(fitted, monkeypatch, parts, message):
    from app.data.dataset import Dataset
    fixed = engine(fitted)
    monkeypatch.setattr(Dataset, "sensor_matrix", lambda *_args: pytest.fail("Scored a rejected case"))
    with pytest.raises(ValueError, match=message):
        fixed.evaluate(case(*parts))


def test_runner_rejects_profile_violations_without_using_a_slot(fitted, tmp_path):
    fixed = engine(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget(), [STUCK_PAIR, {"components": [component("temp_bearing"), component("pressure_out")]}])
    summary = ExperimentRunner(store, fixed).run(investigation)
    assert summary.slots_used == 1 and len(summary.rejected) == 1
    assert "declared groups" in store.load(investigation).proposals[1].reason


def test_findings_list_the_assumptions_the_case_relies_on(fitted):
    finding = classify(engine(fitted).evaluate(FaultCase.model_validate(STUCK_PAIR)), FindingCriterion(candidate=LR))
    assert finding.status == "measured_failure"
    assert any("condition-monitoring module" in item for item in finding.assumptions)
    assert any("saturate or stop" in item for item in finding.assumptions)
    assert not any("hydraulic" in item for item in finding.assumptions)
    assert all(item.endswith("(prototype assumption)") for item in finding.assumptions)


def test_policies_without_a_profile_keep_their_identity():
    policy = FaultPolicy(allowed_sensors=("temp_bearing", "vibration_rms"))
    legacy = {key: value for key, value in policy.model_dump(mode="json").items() if key != "profile"}
    assert policy.fingerprint == hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert FaultPolicy.model_validate_json(json.dumps(legacy)) == policy
    assert loadPolicy(PROFILE).fingerprint != FaultPolicy(allowed_sensors=loadPolicy(PROFILE).allowed_sensors).fingerprint


@pytest.mark.parametrize("change,message", [
    (lambda data: data["sensors"].append({"sensor": "extra", "kinds": ["dropout"]}), "match the allowed"),
    (lambda data: data["sensors"][0].update(description="line one\nline two"), "one line"),
    (lambda data: data["constraints"][2].update(sensors=["unknown"]), "name profile sensors"),
    (lambda data: data.update(id="Bad Id"), "pattern"),
])
def test_invalid_profiles_are_rejected(change, message):
    data = json.loads((Path(__file__).resolve().parents[1] / f"backend/app/faults/profiles/{PROFILE}.json").read_text())
    bounds, groups = data.pop("bounds"), data.pop("groups")
    change(data)
    with pytest.raises(ValueError, match=message):
        profile = Profile.model_validate(data)
        FaultPolicy(allowed_sensors=tuple(SYNTHETIC_SENSORS), allowed_groups=tuple(map(tuple, groups)), profile=profile, **bounds)


def test_controller_sends_reviewed_channel_context_through_aliases(fitted, tmp_path):
    from app.config import Settings
    from app.investigator.controller import ControllerLimits, NemotronController
    fixed = engine(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget())
    settings = Settings(mode="full", assistant_provider="nebius", nebius_base_url="https://api.tokenfactory.nebius.com/v1/", nebius_api_key="mock", assistant_live_enabled=True)
    packet = NemotronController(store, fixed, settings).packet(store.get(investigation), ControllerLimits())
    aliases = {sensor: f"channel-{index}" for index, sensor in enumerate(fixed.policy.allowed_sensors, 1)}
    channel = packet["channels"][aliases["oil_particles"]]
    assert channel["kinds"] == ["dropout", "stuck"] and channel["unit"] == "ppm" and "particle" in channel["description"]
    assert packet["channels"][aliases["pressure_out"]]["maxSeveritySd"] == 2.0
    text = json.dumps(packet)
    assert not any(sensor in text for sensor in SYNTHETIC_SENSORS)


def test_scenario_cli_can_use_a_profile(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("scenario_cli", Path(__file__).resolve().parents[1] / "scripts/evaluate_fault_scenarios.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--output", str(tmp_path / "package"), "--profile", PROFILE]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "complete"
    saved = json.loads((tmp_path / "package/evaluation.json").read_text())
    assert saved["policy"]["profile"]["id"] == PROFILE
