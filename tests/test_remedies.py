import json

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion
from app.investigator.reduction import reduce, regressionCase
from app.investigator.remedies import RemedyError, compareRemedy
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
STUCK_PAIR = [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]
NOISY_DRIFT = [component("vibration_rms", kind="drift", severity_sd=1.5, sign=1, ramp_cycles=5, onset_before_failure=80)]


def investigate(fitted, tmp_path, cases, **criterion):
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_experiments=8), [{"components": parts} for parts in cases])
    saveCriterion(store, investigation, FindingCriterion(candidate=LR, **criterion))
    ExperimentRunner(store, engine).run(investigation)
    return engine, store, investigation


def rows(report):
    return {row["label"].split(":")[0]: row for row in report["cases"]}


def test_threshold_remedy_reports_the_fix_and_its_clean_cost(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path, [STUCK_PAIR, [component("temp_bearing")]])
    finding = next(item for item in recordFindings(store, investigation) if item.is_discovery)
    reduce(store, engine, finding.attempt_id, maxExperiments=20)
    report = compareRemedy(store, engine, investigation, "threshold", threshold=.05)
    labels = [row["label"].split(":")[0] for row in report["cases"]]
    assert labels[:2] == ["discovered", "tested"] and "reduced" in labels
    discovered = rows(report)["discovered"]
    assert discovered["original"]["status"] == "measured_failure" and discovered["remedy"]["status"] == "no_measured_failure"
    assert discovered["improved"] and discovered["matchedCohort"] and report["degraded"] == 0
    assert report["clean"]["original"]["histories"] == report["clean"]["remedy"]["histories"] == 22
    assert report["meetsCriteria"] and report["originalContext"] != report["remedyContext"]
    assert report["cost"]["prepareSeconds"] >= 0 and "no deployed model was changed" in report["note"]
    with store.connection() as db:
        assert json.loads(db.execute("SELECT payload FROM remedies WHERE id=?", (report["id"],)).fetchone()[0]) == report
    unchanged = compareRemedy(store, engine, investigation, "threshold", threshold=.9)
    assert not rows(unchanged)["discovered"]["improved"] and rows(unchanged)["discovered"]["remedy"]["status"] == "measured_failure"


def test_a_remedy_that_degrades_other_cases_fails_acceptance(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path, [STUCK_PAIR, NOISY_DRIFT], max_alarm_burden=.02)
    report = compareRemedy(store, engine, investigation, "threshold", threshold=.05)
    tested = rows(report)["tested"]
    assert rows(report)["discovered"]["improved"]
    assert tested["original"]["status"] == "no_measured_failure" and tested["remedy"]["status"] == "measured_failure" and tested["degraded"]
    assert report["degraded"] == 1 and not report["meetsCriteria"]
    assert tested["remedy"]["faultedBurden"] > tested["original"]["faultedBurden"]


def test_regression_suite_is_rerun_and_must_match_the_context(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path, [STUCK_PAIR])
    finding = recordFindings(store, investigation)[0]
    reduction = reduce(store, engine, finding.attempt_id, maxExperiments=20)
    regression = regressionCase(store, reduction["id"])
    otherEngine, other, otherInvestigation = investigate(fitted, tmp_path / "other", [STUCK_PAIR])
    report = compareRemedy(other, otherEngine, otherInvestigation, "threshold", threshold=.5, regressions=[regression])
    assert any(row["label"].startswith("reduced") or row["label"].startswith("regression") for row in report["cases"])
    regression["contextFingerprint"] = "0" * 64
    with pytest.raises(RemedyError, match="different fitted context"):
        compareRemedy(other, otherEngine, otherInvestigation, "threshold", threshold=.5, regressions=[regression])


def test_augmented_retraining_needs_approval_and_uses_a_new_development_context(fitted, tmp_path, monkeypatch):
    from app.data.dataset import Dataset
    engine, store, investigation = investigate(fitted, tmp_path, [STUCK_PAIR])
    with pytest.raises(PermissionError, match="approval"):
        compareRemedy(store, engine, investigation, "augmented")
    original = Dataset.sensor_matrix
    def developmentOnly(dataset, equipment):
        assert equipment not in fitted.splits.holdout
        return original(dataset, equipment)
    monkeypatch.setattr(Dataset, "sensor_matrix", developmentOnly)
    report = compareRemedy(store, engine, investigation, "augmented", approveTraining=True)
    assert report["remedyCandidate"].startswith("xgboost_augmented/") and report["remedyContext"] != report["originalContext"]
    assert report["clean"]["remedy"]["histories"] == 22 and report["cases"][0]["matchedCohort"]
    assert report["cost"]["prepareSeconds"] > 0


def test_invalid_requests_are_refused(fitted, tmp_path):
    engine, store, investigation = investigate(fitted, tmp_path, [[component("temp_bearing")]])
    with pytest.raises(RemedyError, match="Unknown remedy"):
        compareRemedy(store, engine, investigation, "magic")
    with pytest.raises(RemedyError, match="No measured failure"):
        compareRemedy(store, engine, investigation, "threshold", threshold=.5)
    engine, store, investigation = investigate(fitted, tmp_path / "second", [STUCK_PAIR])
    with pytest.raises(RemedyError, match="explicit threshold"):
        compareRemedy(store, engine, investigation, "threshold")


def test_cli_compares_a_remedy(fitted, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    engine, store, investigation = investigate(fitted, tmp_path, [STUCK_PAIR])
    spec = importlib.util.spec_from_file_location("remedy_cli", Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.context = lambda _args: engine
    assert cli.main(["--store", str(tmp_path / "store"), "--remedy", investigation, "threshold", "--threshold", "0.05"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["kind"] == "threshold" and report["improved"] == 1
