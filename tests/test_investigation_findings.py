"""Deterministic finding classification from recorded evaluations."""
import sqlite3

import numpy as np
import pytest

from app.faults.evaluator import FixedDevelopmentEvaluator, prediction_digest
from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore
from app.faults.scenarios import FaultCase, FaultPolicy
from app.investigator.findings import (FindingCriterion, classify, classifyInvestigation, loadCriterion, recordFindings,
    saveCriterion, summarize)
from app.scoring.metrics import aggregate, score_engine
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR, AGE = "logistic_regression/lr-probe", "age_baseline/age-probe"
# A fragile warning rule loses real useful warnings when two channels freeze 60 cycles before failure.
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60),
    component("oil_particles", kind="stuck", onset_before_failure=60)]}
NOISY_DRIFT = {"components": [component("vibration_rms", kind="drift", severity_sd=3.0, sign=1, ramp_cycles=5, onset_before_failure=80)]}
UNREACHABLE = {"components": [component(onset_before_failure=500)]}


def fixed(fitted, lr=.95):
    return FixedDevelopmentEvaluator(fitted, {LR: lr, AGE: 60.0}, FaultPolicy(allowed_sensors=("temp_bearing", "vibration_rms", "oil_particles")))


def evaluate(engine, scenario):
    return engine.evaluate(FaultCase.model_validate(scenario))


def warningEvaluation(fitted, *, lost=6, early=False):
    # Explicit warning traces test classification boundaries independently of the learned fit.
    evaluation = evaluate(fixed(fitted), STUCK_PAIR)
    model = next(item for item in evaluation.models if item.candidate == LR)
    cycles = np.arange(1, 101)
    rul = 100 - cycles
    cleanScores = (rul <= 15).astype(float)
    clean, faulted = [], []
    for index, pair in enumerate(model.pairs):
        scores = cleanScores.copy()
        if index < lost:
            scores = (rul <= 3).astype(float) if index % 3 == 0 else np.zeros(len(cycles))
        if early:
            scores[(rul >= 55) & (rul <= 57)] = 1
        before = score_engine(pair.equipment_id, cleanScores, cycles, rul, model.threshold, config=fitted.config)
        after = score_engine(pair.equipment_id, scores, cycles, rul, model.threshold, config=fitted.config)
        clean.append(before)
        faulted.append(after)
        pair.clean, pair.faulted = before.outcome, after.outcome
        pair.clean_prediction_digest = prediction_digest(cleanScores, cycles)
        pair.faulted_prediction_digest = prediction_digest(scores, cycles)
    model.clean_all = model.clean_matched = aggregate(clean, config=fitted.config)
    model.faulted = aggregate(faulted, config=fitted.config)
    model.detection_delta = model.faulted.detection_fraction - model.clean_matched.detection_fraction
    model.alarm_burden_delta = model.faulted.early_alarm_burden - model.clean_matched.early_alarm_burden
    return evaluation


def test_lost_useful_warnings_are_a_measured_failure_with_per_history_support(fitted):
    evaluation = warningEvaluation(fitted)
    finding = classify(evaluation, FindingCriterion(candidate=LR))
    assert finding.status == "measured_failure" and finding.is_discovery and finding.reasons == ()
    effects = {effect.kind: effect.histories for effect in finding.effects}
    assert set(effects) == {"missed_warnings", "late_warnings"}
    assert len(effects["missed_warnings"]) + len(effects["late_warnings"]) == 6
    support = {row.equipment_id: row for row in finding.support}
    for kind, state in (("missed_warnings", "missed"), ("late_warnings", "late")):
        assert all(support[e].clean == "detected" and support[e].faulted == state for e in effects[kind])
    assert finding.coverage == 1 and finding.clean_detection == 1 and finding.faulted_detection < finding.clean_detection
    assert finding.scenario_id == evaluation.scenario_id and len(finding.evidence_digest) == 64


def test_classification_is_deterministic_from_the_saved_evaluation(fitted):
    evaluation = evaluate(fixed(fitted), STUCK_PAIR)
    criterion = FindingCriterion(candidate=LR)
    restored = type(evaluation).model_validate_json(evaluation.model_dump_json())
    assert classify(evaluation, criterion) == classify(restored, criterion)
    assert classify(evaluation, criterion).model_dump_json() == classify(evaluate(fixed(fitted), STUCK_PAIR), criterion).model_dump_json()


def test_unchanged_or_below_threshold_outcomes_are_not_discoveries(fitted):
    evaluation = warningEvaluation(fitted)
    assert classify(evaluation, FindingCriterion(candidate=AGE)).status == "no_measured_failure"
    stricter = classify(evaluation, FindingCriterion(candidate=LR, min_lost_warnings=7))
    assert stricter.status == "no_measured_failure" and stricter.effects == () and stricter.support
    with pytest.raises(ValueError, match="target model"):
        classify(evaluation, FindingCriterion(candidate="unknown/model"))


def test_alarm_burden_counts_only_when_unacceptable_and_consequential(fitted):
    evaluation = warningEvaluation(fitted, lost=0, early=True)
    lenient = classify(evaluation, FindingCriterion(candidate=LR))
    assert lenient.status == "no_measured_failure" and lenient.faulted_burden > lenient.clean_burden
    strict = classify(evaluation, FindingCriterion(candidate=LR, max_alarm_burden=.02, min_burden_increase=.01))
    assert strict.status == "measured_failure" and [effect.kind for effect in strict.effects] == ["alarm_burden"]
    assert strict.effects[0].faulted_value == strict.faulted_burden and strict.effects[0].histories


@pytest.mark.parametrize("lost", [0, 1, 6, 22])
def test_lost_warning_threshold_includes_the_boundary(fitted, lost):
    evaluation = warningEvaluation(fitted, lost=lost)
    finding = classify(evaluation, FindingCriterion(candidate=LR, min_lost_warnings=max(1, lost)))
    assert finding.is_discovery == bool(lost)
    assert sum(len(effect.histories) for effect in finding.effects) == lost
    assert classify(evaluation, FindingCriterion(candidate=LR, min_lost_warnings=lost + 1)).status == "no_measured_failure"


def test_fitted_model_findings_match_measured_history_outcomes(fitted):
    evaluation = evaluate(fixed(fitted), STUCK_PAIR)
    model = next(item for item in evaluation.models if item.candidate == LR)
    expected = {"missed_warnings": {pair.equipment_id for pair in model.pairs if pair.clean.detected and pair.faulted.missed},
        "late_warnings": {pair.equipment_id for pair in model.pairs if pair.clean.detected and pair.faulted.late}}
    finding = classify(evaluation, FindingCriterion(candidate=LR))
    assert finding.is_discovery and model.clean_matched.detected == len(model.pairs)
    assert {effect.kind: set(effect.histories) for effect in finding.effects} == {kind: ids for kind, ids in expected.items() if ids}
    assert sum(map(len, expected.values())) == model.clean_matched.detected - model.faulted.detected


def test_low_coverage_or_a_poor_clean_model_is_inconclusive_not_a_discovery(fitted):
    evaluation = evaluate(fixed(fitted), STUCK_PAIR)
    criterion = FindingCriterion(candidate=LR)
    sparse = evaluation.model_copy(update={"expected_histories": 40})
    finding = classify(sparse, criterion)
    assert finding.status == "inconclusive" and not finding.is_discovery and finding.effects
    assert "Coverage 22/40" in finding.reasons[0]
    assert classify(evaluation, criterion.model_copy(update={"min_histories": 23})).status == "inconclusive"
    poor = evaluation.model_copy(deep=True)
    model = next(item for item in poor.models if item.candidate == LR)
    model.clean_matched.detection_fraction = .5
    assert "Clean model" in classify(poor, criterion).reasons[0]
    model.clean_matched.detection_fraction, model.clean_matched.early_alarm_burden = 1.0, .2
    assert classify(poor, criterion).reasons == ("Clean model already exceeds the acceptable alarm burden",)


def test_no_changed_readings_is_not_applicable(fitted):
    evaluation = evaluate(fixed(fitted), UNREACHABLE)
    assert evaluation.status == "not_applicable"
    finding = classify(evaluation, FindingCriterion(candidate=LR))
    assert finding.status == "not_applicable" and finding.clean_detection is None and finding.support == ()


def test_investigation_findings_separate_invalid_errors_and_failures(fitted, tmp_path, monkeypatch):
    engine = fixed(fitted)
    store = InvestigationStore(tmp_path / "store")
    investigation = store.create(engine, InvestigationBudget(max_attempts_per_scenario=1), [STUCK_PAIR,
        {"components": [component("unknown")]}, NOISY_DRIFT, STUCK_PAIR])
    with pytest.raises(ValueError, match="criterion"):
        classifyInvestigation(store, investigation)
    original = engine.evaluate
    def flaky(case, *, cancelled=None):
        if case.components[0].kind == "drift":
            raise RuntimeError("estimator crashed")
        return original(case, cancelled=cancelled)
    monkeypatch.setattr(engine, "evaluate", flaky)
    ExperimentRunner(store, engine).run(investigation)
    with pytest.raises(ValueError, match="fixed models"):
        saveCriterion(store, investigation, FindingCriterion(candidate="unknown/model"))
    criterion = saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    assert saveCriterion(store, investigation, FindingCriterion(candidate=LR)) == loadCriterion(store, investigation) == criterion
    with pytest.raises(ValueError, match="different finding criterion"):
        saveCriterion(store, investigation, FindingCriterion(candidate=LR, min_lost_warnings=2))

    findings = recordFindings(store, investigation)
    assert sorted(f.status for f in findings) == ["execution_error", "invalid_proposal", "measured_failure"]
    error = next(f for f in findings if f.status == "execution_error")
    assert "estimator crashed" in error.reasons[0] and not error.is_discovery and error.effects == ()
    assert summarize(findings) == {"counts": {"invalid_proposal": 1, "measured_failure": 1, "execution_error": 1},
        "discoveries": [next(f.attempt_id for f in findings if f.is_discovery)], "discoveryFamilies": ["oil_particles:stuck+vibration_rms:stuck"]}
    assert recordFindings(store, investigation) == findings  # Re-reading never changes a classification.

    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE findings SET payload=replace(payload,'measured_failure','no_measured_failure') WHERE status='measured_failure'")
    with pytest.raises(ValueError, match="no longer matches"):
        recordFindings(store, investigation)
