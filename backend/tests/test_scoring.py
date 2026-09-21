"""Alert episodes, operational measures and interval estimates.

These definitions are the substance of the submission's evaluation claim, so each
one is pinned to a hand-constructed case where the right answer is obvious.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import EXPERIMENT
from app.scoring.episodes import alert_state, episodes_from_state
from app.scoring.metrics import aggregate, score_engine
from app.scoring.stats import intervals_overlap, wilson_interval


def series(length: int, failure_cycle: int | None = None):
    """Cycle and remaining-life vectors for a synthetic history."""
    cycles = np.arange(1, length + 1)
    failure = failure_cycle or length
    return cycles, failure - cycles


class TestAlertState:
    def test_a_single_crossing_does_not_open_an_episode(self):
        scores = np.array([0.0, 0.0, 1.0, 0.0, 0.0])
        assert not alert_state(scores, 0.5).any()

    def test_two_consecutive_crossings_open_an_episode(self):
        scores = np.array([0.0, 1.0, 1.0, 1.0, 0.0])
        active = alert_state(scores, 0.5)
        # The alert fires on the second qualifying score, not the first.
        assert active.tolist() == [False, False, True, True, True]

    def test_two_consecutive_low_scores_close_an_episode(self):
        scores = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
        active = alert_state(scores, 0.5)
        assert active.tolist() == [False, True, True, True, False, False]

    def test_a_single_dip_does_not_close_an_episode(self):
        scores = np.array([1.0, 1.0, 0.0, 1.0, 1.0])
        assert alert_state(scores, 0.5).tolist() == [False, True, True, True, True]

    def test_invalid_cycles_neither_open_nor_close(self):
        scores = np.array([1.0, np.nan, 1.0, 1.0])
        valid = np.array([True, False, True, True])
        active = alert_state(scores, 0.5, valid=valid)
        # The run of qualifying observations pauses rather than resetting.
        assert active.tolist() == [False, False, True, True]

    def test_empty_input(self):
        assert alert_state(np.array([]), 0.5).size == 0


class TestEpisodes:
    def test_episode_boundaries_use_cycle_and_remaining_life(self):
        cycles, rul = series(10)
        active = np.array([False] * 3 + [True] * 4 + [False] * 3)
        episodes = episodes_from_state(active, cycles, rul)
        assert len(episodes) == 1
        assert episodes[0].start_cycle == 4
        assert episodes[0].end_cycle == 7
        assert episodes[0].start_rul == 6
        assert episodes[0].end_rul == 3
        assert not episodes[0].still_open_at_failure

    def test_two_separate_episodes(self):
        cycles, rul = series(10)
        active = np.array([True, True, False, False, True, True, False, False, False, False])
        assert len(episodes_from_state(active, cycles, rul)) == 2

    def test_an_episode_open_at_the_end_is_marked(self):
        cycles, rul = series(6)
        active = np.array([False, False, True, True, True, True])
        assert episodes_from_state(active, cycles, rul)[0].still_open_at_failure


class TestEngineOutcomes:
    def test_an_alert_inside_the_useful_window_is_a_detection(self):
        cycles, rul = series(100)
        scores = np.where(rul <= 25, 1.0, 0.0)
        result = score_engine("E1", scores, cycles, rul, 0.5)
        assert result.outcome.detected
        assert not result.outcome.late and not result.outcome.missed
        assert result.outcome.lead_time == 24, "the alert fires on the second qualifying cycle"

    def test_an_alert_only_in_the_final_cycles_is_late_not_missed(self):
        cycles, rul = series(100)
        scores = np.where(rul <= 5, 1.0, 0.0)
        result = score_engine("E1", scores, cycles, rul, 0.5)
        assert result.outcome.late
        assert not result.outcome.detected
        assert not result.outcome.missed

    def test_no_alert_at_all_is_a_miss(self):
        cycles, rul = series(100)
        result = score_engine("E1", np.zeros(100), cycles, rul, 0.5)
        assert result.outcome.missed
        assert not result.outcome.detected and not result.outcome.late

    def test_an_alert_opening_before_the_horizon_keeps_its_earlier_lead_time(self):
        cycles, rul = series(100)
        scores = np.where(rul <= 60, 1.0, 0.0)
        result = score_engine("E1", scores, cycles, rul, 0.5)
        assert result.outcome.detected
        assert result.outcome.lead_time == 59, "lead time may exceed the horizon"

    def test_a_permanent_alarm_produces_a_burden_near_one(self):
        """A model that alerts on everything is caught by the burden, not the detection rate."""
        cycles, rul = series(100)
        result = score_engine("E1", np.ones(100), cycles, rul, 0.5)
        assert result.outcome.detected
        # One eligible cycle escapes: the alert needs two consecutive scores to fire.
        assert result.alarm_eligible_cycles == result.eligible_cycles - 1
        assert aggregate([result]).early_alarm_burden > 0.95

    def test_the_transition_band_is_excluded_from_the_burden(self):
        """An alert that opens between the horizon and the band edge is not a false alarm."""
        cycles, rul = series(100)
        scores = np.where(rul <= EXPERIMENT.transition_band_end, 1.0, 0.0)
        result = score_engine("E1", scores, cycles, rul, 0.5)
        assert result.alarm_eligible_cycles == 0
        assert aggregate([result]).early_alarm_burden == pytest.approx(0.0)

    def test_an_alert_just_outside_the_band_does_count(self):
        cycles, rul = series(100)
        scores = np.where(rul <= EXPERIMENT.transition_band_end + 12, 1.0, 0.0)
        result = score_engine("E1", scores, cycles, rul, 0.5)
        assert result.alarm_eligible_cycles > 0


class TestAggregation:
    def test_counts_are_per_engine_not_per_cycle(self):
        cycles, rul = series(100)
        detected = score_engine("A", np.where(rul <= 20, 1.0, 0.0), cycles, rul, 0.5)
        missed = score_engine("B", np.zeros(100), cycles, rul, 0.5)
        late = score_engine("C", np.where(rul <= 4, 1.0, 0.0), cycles, rul, 0.5)

        metrics = aggregate([detected, missed, late])
        assert metrics.engines == 3
        assert (metrics.detected, metrics.late, metrics.missed) == (1, 1, 1)
        assert metrics.detection_fraction == pytest.approx(1 / 3)

    def test_empty_input_reports_nothing_known(self):
        metrics = aggregate([])
        assert metrics.engines == 0
        assert metrics.detection_ci.lower == 0.0 and metrics.detection_ci.upper == 1.0

    def test_median_lead_time_ignores_engines_without_a_warning(self):
        cycles, rul = series(100)
        first = score_engine("A", np.where(rul <= 20, 1.0, 0.0), cycles, rul, 0.5)
        second = score_engine("B", np.zeros(100), cycles, rul, 0.5)
        assert aggregate([first, second]).median_lead_time == pytest.approx(19.0)


class TestWilson:
    def test_interval_brackets_the_point_estimate(self):
        interval = wilson_interval(14, 20)
        assert interval.lower < 0.7 < interval.upper

    def test_no_trials_means_nothing_is_known(self):
        interval = wilson_interval(0, 0)
        assert (interval.lower, interval.upper) == (0.0, 1.0)

    def test_a_perfect_result_still_carries_uncertainty(self):
        interval = wilson_interval(20, 20)
        assert interval.upper == pytest.approx(1.0)
        assert interval.lower < 0.9, "20 of 20 does not establish a rate above 90%"

    def test_more_trials_narrow_the_interval(self):
        small = wilson_interval(7, 10)
        large = wilson_interval(70, 100)
        assert (large.upper - large.lower) < (small.upper - small.lower)

    def test_overlap_detection(self):
        assert intervals_overlap(wilson_interval(18, 20), wilson_interval(17, 20))
        assert not intervals_overlap(wilson_interval(20, 100), wilson_interval(90, 100))
