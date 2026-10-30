from dataclasses import replace

import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.profiles import loadPolicy
from app.investigator.findings import FindingCriterion, saveCriterion
from app.investigator.reduction import reduce
from app.investigator import validation
from app.investigator.validation import assess, freeze, freshSynthetic, loadValidation
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]}


def engine(fitted, threshold=.95):
    return FixedDevelopmentEvaluator(fitted, {LR: threshold}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))


def fresh(config, seed=7, prefix=None):
    data = freshSynthetic(config, seed)
    if prefix:
        frame = data.frame.copy()
        frame["equipment_id"] = prefix + frame["equipment_id"]
        data = replace(data, frame=frame)
    return data


@pytest.fixture
def investigated(fitted, tmp_path):
    fixed = engine(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget(max_experiments=4), [STUCK_PAIR, {"components": [component("temp_bearing")]}])
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    ExperimentRunner(store, fixed).run(investigation)
    return fixed, store, investigation


def test_a_frozen_procedure_is_assessed_once_on_fresh_histories(investigated, fitted):
    fixed, store, investigation = investigated
    attempt = next(item.id for item in store.load(investigation).attempts if store.result(item.id).scenario.scenario_id.startswith("compound"))
    reduce(store, fixed, attempt, maxExperiments=4)
    frozen = freeze(store, investigation, remedyThreshold=.5)
    labels = [case["label"] for case in frozen["procedure"]["cases"]]
    assert "discovered:oil_particles:stuck+vibration_rms:stuck" in labels and any(label.startswith("reduced:") for label in labels)
    assert frozen["procedure"]["remedy"] == {"kind": "threshold", "threshold": .5} and frozen["status"] == "frozen"
    report = assess(store, frozen["id"], fixed, fresh(fitted.config))
    assert report["status"] == "assessed" and report["freshHistories"] == 12 and report["procedureDigest"] == frozen["procedureDigest"]
    assert report["clean"]["original"]["histories"] == report["clean"]["remedy"]["histories"] == 12
    for row in report["cases"]:
        assert row["original"]["expected"] == 12 and row["original"]["status"] in {"measured_failure", "no_measured_failure", "inconclusive", "not_applicable"}
        assert row["original"]["reproduced"] == (row["original"]["status"] == "measured_failure") and "remedy" in row
    assert loadValidation(store, frozen["id"])["status"] == "assessed"
    with pytest.raises(ValueError, match="already been assessed"):
        assess(store, frozen["id"], fixed, fresh(fitted.config, seed=8))


def test_changing_the_procedure_after_reading_results_needs_new_fresh_histories(investigated, fitted):
    fixed, store, investigation = investigated
    first = freeze(store, investigation)
    assess(store, first["id"], fixed, fresh(fitted.config))
    changed = freeze(store, investigation, remedyThreshold=.5)
    with pytest.raises(ValueError, match="12 of these histories were already seen"):
        assess(store, changed["id"], fixed, fresh(fitted.config, prefix="RENAMED-"))
    assert assess(store, changed["id"], fixed, fresh(fitted.config, seed=9))["status"] == "assessed"


def test_development_histories_cannot_return_as_fresh_ones(investigated, fitted):
    fixed, store, investigation = investigated
    development = fitted.dataset
    frame = development.frame.copy()
    frame["equipment_id"] = "NEW-" + frame["equipment_id"]
    with pytest.raises(ValueError, match="already seen"):
        assess(store, freeze(store, investigation)["id"], fixed, replace(development, frame=frame))


def test_exposure_is_recorded_before_scoring_so_an_interrupted_assessment_cannot_retry(investigated, fitted, monkeypatch):
    fixed, store, investigation = investigated
    frozen = freeze(store, investigation)

    def broken(*args, **kwargs):
        raise RuntimeError("worker lost")
    monkeypatch.setattr(validation, "freshContext", broken)
    with pytest.raises(RuntimeError):
        assess(store, frozen["id"], fixed, fresh(fitted.config))
    monkeypatch.undo()
    assert loadValidation(store, frozen["id"])["status"] == "assessing"
    with pytest.raises(ValueError, match="already"):
        assess(store, frozen["id"], fixed, fresh(fitted.config))


def test_freezing_needs_a_criterion_and_something_measured(fitted, tmp_path):
    fixed = engine(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(fixed, InvestigationBudget(max_experiments=3), [{"components": [component("temp_bearing")]}])
    with pytest.raises(ValueError, match="criterion"):
        freeze(store, investigation)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    ExperimentRunner(store, fixed).run(investigation)
    with pytest.raises(ValueError, match="Nothing to validate"):
        freeze(store, investigation)


def test_assessment_needs_the_investigation_context(investigated, fitted):
    _, store, investigation = investigated
    with pytest.raises(ValueError, match="fixed evaluation context"):
        assess(store, freeze(store, investigation)["id"], engine(fitted, .9), fresh(fitted.config))


def test_cli_freezes_and_validates_on_fresh_synthetic_histories(investigated, fitted, tmp_path, capsys):
    import importlib.util
    import json
    from pathlib import Path
    fixed, store, investigation = investigated
    spec = importlib.util.spec_from_file_location("validate_cli", Path(__file__).resolve().parents[1] / "scripts/run_fault_investigation.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.context = lambda args: engine(fitted)
    assert cli.main(["--store", str(tmp_path / "store"), "--freeze", investigation, "--threshold", "0.5"]) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert cli.main(["--store", str(tmp_path / "store"), "--validate", frozen["id"], "--fresh-synthetic", "11", "--fresh-count", "10"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "assessed" and report["freshHistories"] == 10 and report["procedure"]["remedy"]["threshold"] == .5
