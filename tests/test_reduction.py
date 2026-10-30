import json

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.faults.scenarios import FaultPolicy
from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion
from app.investigator.reduction import ReductionError, checkRegression, loadReduction, reduce, regressionCase
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
DRIFT_PAIR = [component("vibration_rms", kind="drift", severity_sd=3.0, sign=-1, ramp_cycles=40, onset_before_failure=80),
    component("oil_particles", kind="stuck", onset_before_failure=60)]
WITH_BYSTANDER = [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60),
    component("ambient_temp", onset_before_failure=40)]


def investigate(fitted, tmp_path, parts, policy=None):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, policy or loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_experiments=4), [{"components": parts}])
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    ExperimentRunner(store, engine).run(investigation)
    finding = recordFindings(store, investigation)[0]
    return engine, store, investigation, finding


def test_reduction_reproduces_then_simplifies_on_explicit_grids(fitted, tmp_path):
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    assert finding.status == "measured_failure"
    reduction = reduce(store, engine, finding.attempt_id, maxExperiments=40)
    steps = reduction["steps"]
    assert reduction["status"] == "complete" and steps[0]["change"] == "reproduce original" and steps[0]["accepted"]
    assert {step["change"] for step in steps if step["change"].startswith("remove")} == {"remove oil_particles", "remove vibration_rms"}
    assert all(step["status"] == "measured_failure" for step in steps if step["accepted"])
    assert not any("ramp_cycles" in step["change"] for step in steps)
    final = {atom["sensor"]: atom for atom in reduction["final"]["components"]}
    assert final["vibration_rms"]["onset_before_failure"] < 80 and final["oil_particles"]["onset_before_failure"] < 60
    assert final["vibration_rms"]["severity_sd"] == 3.0
    tried = [step for step in steps if step["change"].startswith("set vibration_rms severity_sd")]
    assert [step["scenario"]["components"][1]["severity_sd"] for step in tried] == [0.5, 1.0, 1.5, 2.0, 2.5]
    assert reduction["claims"][0].startswith("Component-minimal") and "global minimum" in reduction["claims"][-1]
    assert loadReduction(store, reduction["id"]) == reduction
    assert 0 < reduction["experiments"] <= 40 and all("cohortChanged" in step for step in steps if "evidenceDigest" in step)


def test_irrelevant_components_are_removed(fitted, tmp_path):
    policy = FaultPolicy(allowed_sensors=("vibration_rms", "oil_particles", "ambient_temp"), max_components=3, max_evaluations=128)
    engine, store, investigation, finding = investigate(fitted, tmp_path, WITH_BYSTANDER, policy)
    reduction = reduce(store, engine, finding.attempt_id, maxExperiments=60)
    accepted = [step["change"] for step in reduction["steps"] if step["accepted"]]
    assert accepted[:2] == ["reproduce original", "remove ambient_temp"]
    assert {atom["sensor"] for atom in reduction["final"]["components"]} == {"oil_particles", "vibration_rms"}
    assert reduction["family"] == "oil_particles:stuck+vibration_rms:stuck"


def test_reduction_work_is_not_counted_as_new_investigation_findings(fitted, tmp_path):
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    before = store.load(investigation)
    reduce(store, engine, finding.attempt_id, maxExperiments=12)
    after = store.load(investigation)
    assert after.slots_used == before.slots_used and len(after.proposals) == len(before.proposals)
    assert [item.status for item in recordFindings(store, investigation)] == ["measured_failure"]


def test_allowance_exhaustion_is_partial_and_claims_only_what_was_tested(fitted, tmp_path):
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    reduction = reduce(store, engine, finding.attempt_id, maxExperiments=1)
    assert reduction["status"] == "partial" and reduction["experiments"] == 1
    assert [step["change"] for step in reduction["steps"]] == ["reproduce original", "remove oil_particles"]
    assert reduction["claims"] == ["Not a proof of a global minimum."]
    assert reduction["final"] == reduction["original"]


def test_only_measured_failures_with_a_criterion_can_be_reduced(fitted, tmp_path):
    engine, store, investigation, finding = investigate(fitted, tmp_path, [component("temp_bearing")])
    assert finding.status != "measured_failure"
    with pytest.raises(ReductionError, match="measured failure"):
        reduce(store, engine, finding.attempt_id)
    other = InvestigationStore(tmp_path / "other")
    plain = other.create(engine, InvestigationBudget(), [{"components": DRIFT_PAIR}])
    ExperimentRunner(other, engine).run(plain)
    with pytest.raises(ReductionError, match="criterion"):
        reduce(other, engine, other.load(plain).attempts[0].id)
    with pytest.raises(ReductionError, match="allowance"):
        saveCriterion(other, plain, FindingCriterion(candidate=LR))
        reduce(other, engine, other.load(plain).attempts[0].id, maxExperiments=0)


def test_cancellation_and_crashes_are_recorded_and_release_the_lease(fitted, tmp_path, monkeypatch):
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    checks = iter([False, False, True])
    cancelled = reduce(store, engine, finding.attempt_id, cancelled=lambda: next(checks, True))
    assert cancelled["status"] == "cancelled" and cancelled["final"] == cancelled["original"]
    original = engine.evaluate
    calls = []
    def crash(case, *, cancelled=None):
        calls.append(case)
        if len(calls) > 1:
            raise RuntimeError("estimator crashed")
        return original(case, cancelled=cancelled)
    monkeypatch.setattr(engine, "evaluate", crash)
    with pytest.raises(RuntimeError):
        reduce(store, engine, finding.attempt_id)
    with store.connection() as db:
        statuses = [row[0] for row in db.execute("SELECT status FROM reductions ORDER BY created")]
    assert statuses == ["cancelled", "interrupted"]
    monkeypatch.setattr(engine, "evaluate", original)
    assert reduce(store, engine, finding.attempt_id, maxExperiments=4)["status"] in {"complete", "partial"}


def test_regression_case_reproduces_and_is_bound_to_its_context(fitted, tmp_path):
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    reduction = reduce(store, engine, finding.attempt_id, maxExperiments=40)
    regression = regressionCase(store, reduction["id"])
    assert regression["expected"] == "measured_failure" and regression["profile"] == "synthetic-rotating-v1"
    assert regression["source"] == {"investigation": investigation, "attempt": finding.attempt_id, "reduction": reduction["id"]}
    json.dumps(regression)
    result, passed = checkRegression(engine, regression)
    assert passed and result.status == "measured_failure"
    other = FixedDevelopmentEvaluator(fitted, {LR: .9}, engine.policy)
    with pytest.raises(ReductionError, match="different fitted context"):
        checkRegression(other, regression)
    cancelled = reduce(store, engine, finding.attempt_id, cancelled=lambda: True)
    with pytest.raises(ReductionError, match="finished reduction"):
        regressionCase(store, cancelled["id"])


def test_cli_reduces_and_exports_a_regression_case(fitted, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    engine, store, investigation, finding = investigate(fitted, tmp_path, DRIFT_PAIR)
    spec = importlib.util.spec_from_file_location("reduce_cli", Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.context = lambda _args: engine
    assert cli.main(["--store", str(tmp_path / "store"), "--reduce", finding.attempt_id, "--max-reduction-experiments", "40"]) == 0
    reduction = json.loads(capsys.readouterr().out)
    assert reduction["status"] == "complete"
    output = tmp_path / "regression.json"
    assert cli.main(["--store", str(tmp_path / "store"), "--regression", reduction["id"], str(output)]) == 0
    assert json.loads(output.read_text())["scenarioId"] == reduction["finalScenarioId"]
