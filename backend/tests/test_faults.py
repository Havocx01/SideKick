"""Fault injection semantics."""

from __future__ import annotations

import numpy as np
import pytest

from app.config import EXPERIMENT
from app.faults.inject import apply_fault, resolve_onset
from app.faults.matrix import (
    describe_matrix,
    full_scenarios,
    random_onset_scenarios,
    required_scenarios,
)
from app.schemas import FaultDuration, FaultKind, FaultSpec


def history(length: int = 120):
    values = 100.0 + np.arange(length, dtype=float) * 0.5
    rul = (length - 1) - np.arange(length)
    return values, rul


def spec(kind: FaultKind, **kwargs) -> FaultSpec:
    defaults = {
        "duration": FaultDuration.persistent,
        "sensor": "s1",
        "onset_before_failure": 60,
    }
    return FaultSpec(kind=kind, **{**defaults, **kwargs})


class TestOnset:
    def test_onset_is_located_by_cycles_before_failure(self):
        _, rul = history(120)
        index, reason = resolve_onset(rul, spec(FaultKind.stuck, onset_before_failure=60), EXPERIMENT)
        assert reason is None
        assert rul[index] == 60

    def test_a_history_too_short_to_reach_the_onset_is_skipped(self):
        _, rul = history(30)
        index, reason = resolve_onset(rul, spec(FaultKind.stuck, onset_before_failure=200), EXPERIMENT)
        assert index is None
        assert "never reaches" in reason

    def test_random_onset_is_reproducible_from_its_seed(self):
        _, rul = history(150)
        seeded = spec(FaultKind.dropout, onset_before_failure=None, seed=4242)
        first, _ = resolve_onset(rul, seeded, EXPERIMENT)
        second, _ = resolve_onset(rul, seeded, EXPERIMENT)
        assert first == second

    def test_different_seeds_place_the_fault_differently(self):
        _, rul = history(200)
        positions = {
            resolve_onset(rul, spec(FaultKind.dropout, onset_before_failure=None, seed=s), EXPERIMENT)[0]
            for s in range(30)
        }
        assert len(positions) > 1


class TestDropout:
    def test_readings_stop_at_the_onset_and_never_return(self):
        values, rul = history()
        result = apply_fault(values, rul, spec(FaultKind.dropout), sensor_std=1.0)
        assert result.applied
        onset = result.onset_index
        assert np.isfinite(result.values[:onset]).all()
        assert np.isnan(result.values[onset:]).all(), "a persistent fault does not heal"

    def test_a_transient_dropout_lasts_the_stated_length(self):
        values, rul = history()
        result = apply_fault(
            values,
            rul,
            spec(FaultKind.dropout, duration=FaultDuration.transient, length=10),
            sensor_std=1.0,
        )
        onset = result.onset_index
        assert np.isnan(result.values[onset : onset + 10]).all()
        assert np.isfinite(result.values[onset + 10 :]).all()
        assert result.affected_cycles == 10

    def test_the_original_series_is_not_modified(self):
        values, rul = history()
        original = values.copy()
        apply_fault(values, rul, spec(FaultKind.dropout), sensor_std=1.0)
        assert np.array_equal(values, original)


class TestStuck:
    def test_the_last_good_reading_is_held(self):
        values, rul = history()
        result = apply_fault(values, rul, spec(FaultKind.stuck), sensor_std=1.0)
        onset = result.onset_index
        held = values[onset - 1]
        assert np.allclose(result.values[onset:], held)
        assert np.array_equal(result.values[:onset], values[:onset])

    def test_a_stuck_sensor_still_reads_a_plausible_value(self):
        """This is why a stuck sensor is dangerous: nothing looks missing."""
        values, rul = history()
        result = apply_fault(values, rul, spec(FaultKind.stuck), sensor_std=1.0)
        assert np.isfinite(result.values).all()
        assert result.values.min() >= values.min()


class TestDrift:
    def test_the_offset_ramps_then_holds(self):
        values, rul = history()
        result = apply_fault(
            values,
            rul,
            spec(FaultKind.drift, severity_sd=2.0, sign=1, ramp_cycles=20),
            sensor_std=3.0,
        )
        onset = result.onset_index
        offset = result.values[onset:] - values[onset:]
        assert offset[0] == pytest.approx(6.0 / 20)
        assert offset[19] == pytest.approx(6.0), "full magnitude is 2 SD of 3.0"
        assert np.allclose(offset[19:], 6.0), "drift does not heal"

    def test_the_sign_sets_the_direction(self):
        values, rul = history()
        upward = apply_fault(values, rul, spec(FaultKind.drift, severity_sd=1.0, sign=1), sensor_std=2.0)
        downward = apply_fault(values, rul, spec(FaultKind.drift, severity_sd=1.0, sign=-1), sensor_std=2.0)
        assert upward.values[-1] > values[-1]
        assert downward.values[-1] < values[-1]

    def test_severity_scales_with_the_training_standard_deviation(self):
        values, rul = history()
        narrow = apply_fault(values, rul, spec(FaultKind.drift, severity_sd=1.0, sign=1), sensor_std=1.0)
        wide = apply_fault(values, rul, spec(FaultKind.drift, severity_sd=1.0, sign=1), sensor_std=10.0)
        assert (wide.values[-1] - values[-1]) == pytest.approx(10 * (narrow.values[-1] - values[-1]))

    def test_a_channel_with_no_variation_cannot_drift(self):
        values, rul = history()
        result = apply_fault(values, rul, spec(FaultKind.drift, severity_sd=1.0), sensor_std=0.0)
        assert not result.applied
        assert "no training variation" in result.reason


class TestScenarioMatrix:
    def test_the_required_set_covers_every_sensor_and_every_kind(self):
        sensors = ["a", "b", "c"]
        specs = required_scenarios(sensors, EXPERIMENT)
        assert {s.sensor for s in specs} == set(sensors)
        assert {s.kind for s in specs} == set(FaultKind)
        assert all(s.duration == FaultDuration.persistent for s in specs)
        # Drift is tested in both directions, so insensitivity one way cannot pass.
        assert {s.sign for s in specs if s.kind == FaultKind.drift} == {-1, 1}

    def test_the_required_set_uses_only_the_earlier_onset(self):
        specs = required_scenarios(["a"], EXPERIMENT)
        assert {s.onset_before_failure for s in specs} == {max(EXPERIMENT.fault_onsets)}

    def test_the_required_set_is_contained_in_the_full_set(self):
        required = {s.scenario_id for s in required_scenarios(["a", "b"], EXPERIMENT)}
        full = {s.scenario_id for s in full_scenarios(["a", "b"], EXPERIMENT)}
        assert required <= full

    def test_scenario_identifiers_are_unique(self):
        specs = full_scenarios(["a", "b", "c"], EXPERIMENT)
        assert len({s.scenario_id for s in specs}) == len(specs)

    def test_random_onset_scenarios_carry_distinct_seeds(self):
        specs = random_onset_scenarios(["a"], EXPERIMENT, repeats=3)
        seeds = [s.seed for s in specs]
        assert all(s is not None for s in seeds)
        assert len(set(seeds)) == len(seeds)

    def test_counts_scale_with_the_sensor_list(self):
        one = describe_matrix(["a"], EXPERIMENT)
        two = describe_matrix(["a", "b"], EXPERIMENT)
        assert two["required"] == 2 * one["required"]
        assert two["full"] == 2 * one["full"]

    def test_a_spec_describes_itself_readably(self):
        described = spec(FaultKind.drift, severity_sd=2.0, sign=-1).label()
        assert "Drift" in described and "2 SD down" in described and "60 cycles out" in described
