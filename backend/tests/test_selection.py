"""The selection rule, thresholds and calibration."""

from __future__ import annotations

import numpy as np
import pytest

from app.models.calibration import brier_score, calibration_report, reliability_bins
from app.models.thresholds import candidate_thresholds, choose_threshold
from app.schemas import (
    AcceptanceCriteria,
    AlertMetrics,
    CandidateKind,
    Partition,
    ScenarioResult,
    SelectionOutcome,
)
from app.scoring.selection import build_verdict, meets, select
from app.scoring.stats import wilson_interval

CRITERIA = AcceptanceCriteria(
    min_detection_fraction=0.70,
    max_early_alarm_burden=0.05,
    min_useful_lead=10,
    horizon_cycles=30,
)


def metrics(detection: float, burden: float = 0.0, engines: int = 20) -> AlertMetrics:
    detected = round(detection * engines)
    return AlertMetrics(
        engines=engines,
        detected=detected,
        late=engines - detected,
        missed=0,
        detection_fraction=detection,
        detection_ci=wilson_interval(detected, engines),
        early_alarm_burden=burden,
        new_episodes_per_1000=1.0,
        median_lead_time=20.0,
        eligible_cycles=1000,
        scored_cycles=2000,
    )


def scenario(scenario_id: str, detection: float, burden: float = 0.0) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        candidate=CandidateKind.xgboost,
        config_id="x1",
        partition=Partition.out_of_fold,
        threshold=0.5,
        metrics=metrics(detection, burden),
        required=True,
    )


class TestCriteria:
    def test_both_conditions_must_hold(self):
        assert meets(metrics(0.9, 0.01), CRITERIA)
        assert not meets(metrics(0.5, 0.01), CRITERIA), "detection too low"
        assert not meets(metrics(0.9, 0.5), CRITERIA), "too many early alarms"

    def test_the_boundary_is_inclusive(self):
        assert meets(metrics(0.70, 0.05), CRITERIA)


class TestVerdicts:
    def test_a_candidate_failing_one_required_case_does_not_qualify(self):
        verdict = build_verdict(
            candidate=CandidateKind.xgboost,
            config_id="x1",
            threshold=0.5,
            clean=metrics(1.0),
            required=[scenario("a", 0.95), scenario("b", 0.40)],
            criteria=CRITERIA,
        )
        assert not verdict.qualifies
        assert verdict.required_passed == 1
        assert verdict.worst_scenario_id == "b"
        assert any("fall short" in note for note in verdict.notes)

    def test_strong_clean_performance_alone_does_not_qualify(self):
        verdict = build_verdict(
            candidate=CandidateKind.logistic_regression,
            config_id="lr1",
            threshold=0.9,
            clean=metrics(1.0),
            required=[scenario("a", 0.10)],
            criteria=CRITERIA,
        )
        assert verdict.passes_clean
        assert not verdict.qualifies

    def test_a_candidate_with_no_fault_results_cannot_qualify(self):
        """Untested robustness is not the same as demonstrated robustness."""
        verdict = build_verdict(
            candidate=CandidateKind.xgboost,
            config_id="x1",
            threshold=0.5,
            clean=metrics(1.0),
            required=[],
            criteria=CRITERIA,
        )
        assert not verdict.qualifies

    def test_the_drop_from_clean_to_worst_case_is_reported(self):
        verdict = build_verdict(
            candidate=CandidateKind.xgboost,
            config_id="x1",
            threshold=0.5,
            clean=metrics(1.0),
            required=[scenario("a", 0.75)],
            criteria=CRITERIA,
        )
        assert verdict.qualifies
        assert any("25% detection" in note for note in verdict.notes)


class TestSelect:
    def _verdict(self, kind, config_id, clean, required):
        return build_verdict(
            candidate=kind,
            config_id=config_id,
            threshold=0.5,
            clean=clean,
            required=required,
            criteria=CRITERIA,
        )

    def test_ranking_is_by_mean_detection_under_fault(self):
        strong = self._verdict(CandidateKind.xgboost, "x1", metrics(1.0), [scenario("a", 0.95)])
        weak = self._verdict(CandidateKind.xgboost, "x2", metrics(1.0), [scenario("a", 0.80)])
        result = select([weak, strong], CRITERIA)
        assert result.outcome == SelectionOutcome.qualified
        assert result.ranked[0].config_id == "x1"
        assert result.recommended.config_id == "x1"

    def test_no_candidate_qualifying_is_a_valid_outcome(self):
        poor = self._verdict(CandidateKind.xgboost, "x1", metrics(1.0), [scenario("a", 0.2)])
        result = select([poor], CRITERIA)
        assert result.outcome == SelectionOutcome.none_qualified
        assert result.recommended is None
        assert any("No candidate" in note for note in result.notes)

    def test_qualifying_candidates_outrank_non_qualifying_ones(self):
        """Even a higher mean does not promote a candidate that failed a case."""
        failing = self._verdict(
            CandidateKind.xgboost, "x1", metrics(1.0), [scenario("a", 0.99), scenario("b", 0.1)]
        )
        passing = self._verdict(CandidateKind.xgboost, "x2", metrics(0.9), [scenario("a", 0.75)])
        result = select([failing, passing], CRITERIA)
        assert result.ranked[0].config_id == "x2"
        assert result.recommended.config_id == "x2"

    def test_overlapping_intervals_are_reported_as_unestablished(self):
        first = self._verdict(CandidateKind.xgboost, "x1", metrics(0.95), [scenario("a", 0.95)])
        second = self._verdict(CandidateKind.xgboost, "x2", metrics(0.90), [scenario("a", 0.90)])
        result = select([first, second], CRITERIA)
        assert result.uncertain_comparisons

    def test_a_small_engine_count_is_flagged(self):
        verdict = self._verdict(
            CandidateKind.xgboost, "x1", metrics(0.9, engines=20), [scenario("a", 0.9)]
        )
        result = select([verdict], CRITERIA)
        assert any("20 engines" in note for note in result.notes)


class TestThresholds:
    def test_thresholds_span_the_observed_score_range(self):
        scores = np.linspace(0.0, 1.0, 500)
        grid = candidate_thresholds(scores, grid=20)
        assert grid.min() >= 0.0
        assert grid.max() > scores.max(), "a 'never alert' threshold must be reachable"
        assert len(np.unique(grid)) == len(grid)

    def test_the_grid_works_for_non_probability_scores(self):
        """The age baseline scores in cycles, not probabilities."""
        grid = candidate_thresholds(np.arange(50.0, 400.0), grid=10)
        assert grid.min() > 40.0

    def test_the_chosen_threshold_maximises_detection_inside_the_budget(self):
        scores = np.linspace(0.0, 1.0, 200)

        def evaluate(threshold: float) -> AlertMetrics:
            # Detection falls and burden rises as the threshold drops.
            return metrics(detection=1.0 - threshold, burden=max(0.0, 0.3 - threshold * 0.3))

        choice = choose_threshold(scores, evaluate, CRITERIA)
        assert choice.within_budget
        assert choice.metrics.early_alarm_burden <= CRITERIA.max_early_alarm_burden

    def test_an_unreachable_budget_is_reported_not_relaxed(self):
        scores = np.linspace(0.0, 1.0, 50)
        choice = choose_threshold(scores, lambda t: metrics(0.9, burden=0.9), CRITERIA)
        assert not choice.within_budget
        assert "No threshold" in choice.note


class TestCalibration:
    def test_a_perfect_forecast_scores_zero(self):
        labels = np.array([0, 0, 1, 1])
        assert brier_score(labels, labels.astype(float)) == pytest.approx(0.0)

    def test_a_confidently_wrong_forecast_scores_one(self):
        assert brier_score(np.array([1, 1]), np.array([0.0, 0.0])) == pytest.approx(1.0)

    def test_empty_bins_are_omitted(self):
        scores = np.concatenate([np.full(50, 0.05), np.full(50, 0.95)])
        labels = np.concatenate([np.zeros(50), np.ones(50)])
        bins = reliability_bins(labels, scores, n_bins=10)
        assert all(b.count > 0 for b in bins)
        assert len(bins) == 2

    def test_a_report_records_the_partition(self):
        report = calibration_report(
            candidate=CandidateKind.xgboost,
            config_id="x1",
            labels=np.array([0, 1, 0, 1]),
            scores=np.array([0.1, 0.9, 0.2, 0.8]),
        )
        assert report.partition == Partition.out_of_fold
        assert report.brier < 0.1
