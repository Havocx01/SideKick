"""The data contract, profiling and partitions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.data.contract import ContractError, build_dataset, infer_mapping, validate_mapping
from app.data.profiler import profile_dataset
from app.models.splits import fold_pairs, make_splits, validate_splits
from app.schemas import ColumnMapping, Severity


def raw_frame(n_units: int = 3, length: int = 40, **extra) -> pd.DataFrame:
    rows = []
    for unit in range(1, n_units + 1):
        cycles = np.arange(1, length + 1)
        rows.append(
            pd.DataFrame(
                {
                    "unit_number": unit,
                    "time_in_cycles": cycles,
                    "sensor_a": 100.0 + cycles * 0.4,
                    "sensor_b": 50.0 - cycles * 0.2,
                    **extra,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


class TestMappingInference:
    def test_conventional_names_are_recognised(self):
        mapping = infer_mapping(raw_frame())
        assert mapping.equipment_id == "unit_number"
        assert mapping.cycle_index == "time_in_cycles"
        assert set(mapping.sensors) == {"sensor_a", "sensor_b"}
        assert mapping.inferred

    def test_an_unnamed_identifier_is_inferred_but_flagged_as_ambiguous(self):
        frame = raw_frame().rename(columns={"unit_number": "thing", "time_in_cycles": "step_no"})
        mapping = infer_mapping(frame)
        assert mapping.equipment_id == "thing"
        # The engineer is asked to confirm rather than the guess being silent.
        assert "thing" in mapping.ambiguous

    def test_a_failure_cycle_column_is_taken_as_the_label(self):
        frame = raw_frame()
        frame["failure_cycle"] = 40
        mapping = infer_mapping(frame)
        assert mapping.failure_cycle == "failure_cycle"
        assert "failure_cycle" not in mapping.sensors

    def test_a_frame_with_no_identifier_is_rejected(self):
        frame = pd.DataFrame({"cycle": [1, 2, 3], "sensor_a": [1.0, 2.0, 3.0]})
        # Every value is distinct, so nothing can group the readings.
        with pytest.raises(ContractError, match="identifies the piece of equipment"):
            infer_mapping(frame)

    def test_a_frame_with_no_numeric_sensor_is_rejected(self):
        frame = pd.DataFrame(
            {"unit": ["a", "a", "b"], "cycle": [1, 2, 1], "note": ["x", "y", "z"]}
        )
        with pytest.raises(ContractError, match="no numeric sensor"):
            infer_mapping(frame)

    def test_validation_rejects_a_column_in_two_roles(self):
        frame = raw_frame()
        mapping = ColumnMapping(
            equipment_id="unit_number", cycle_index="time_in_cycles", sensors=["time_in_cycles"]
        )
        with pytest.raises(ContractError, match="two roles"):
            validate_mapping(frame, mapping)


class TestBuildDataset:
    def test_remaining_life_counts_down_to_the_failure_cycle(self):
        dataset = build_dataset(raw_frame(), dataset_id="t", source="test")
        first = dataset.engine_frame(dataset.equipment_ids[0])
        assert first["rul"].iloc[-1] == 0
        assert first["rul"].iloc[0] == 39
        assert (first["rul"].diff().dropna() == -1).all()

    def test_readings_after_the_recorded_failure_are_rejected(self):
        frame = raw_frame()
        frame["failure_cycle"] = 10
        with pytest.raises(ContractError, match="after their recorded failure"):
            build_dataset(frame, dataset_id="t", source="test")

    def test_rows_are_sorted_by_equipment_then_cycle(self):
        shuffled = raw_frame().sample(frac=1.0, random_state=0).reset_index(drop=True)
        dataset = build_dataset(shuffled, dataset_id="t", source="test")
        for equipment_id in dataset.equipment_ids:
            cycles = dataset.engine_frame(equipment_id)["cycle"].to_numpy()
            assert (np.diff(cycles) > 0).all()

    def test_the_hash_depends_on_the_readings(self):
        first = build_dataset(raw_frame(), dataset_id="t", source="test")
        altered = raw_frame()
        altered.loc[5, "sensor_a"] += 0.001
        second = build_dataset(altered, dataset_id="t", source="test")
        assert first.data_hash != second.data_hash

    def test_the_hash_is_stable_across_identical_inputs(self):
        first = build_dataset(raw_frame(), dataset_id="t", source="test")
        second = build_dataset(raw_frame(), dataset_id="t", source="test")
        assert first.data_hash == second.data_hash

    def test_the_label_marks_exactly_the_horizon(self, config):
        dataset = build_dataset(raw_frame(length=80), dataset_id="t", source="test", config=config)
        labels = dataset.label_vector()
        rul = dataset.frame["rul"].to_numpy()
        assert set(rul[labels == 1]) == set(range(1, config.horizon_cycles + 1))
        assert 0 not in rul[labels == 1], "the failure cycle is not a positive label"


class TestProfiler:
    def test_a_healthy_dataset_is_usable(self, dataset):
        assert profile_dataset(dataset).usable

    def test_duplicate_readings_block_evaluation(self, config):
        frame = raw_frame(n_units=30, length=80)
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        dataset = build_dataset(frame, dataset_id="t", source="test", config=config)
        profile = profile_dataset(dataset, config=config)
        assert not profile.usable
        assert any(f.code == "DUPLICATE_READINGS" for f in profile.findings)

    def test_a_single_history_cannot_support_unseen_equipment_evaluation(self, config):
        dataset = build_dataset(
            raw_frame(n_units=1, length=90), dataset_id="t", source="test", config=config
        )
        profile = profile_dataset(dataset, config=config)
        assert not profile.usable
        assert any(f.code == "SINGLE_EQUIPMENT" for f in profile.findings)

    def test_too_few_histories_for_the_partitions_is_a_blocker(self, config):
        dataset = build_dataset(
            raw_frame(n_units=3, length=90), dataset_id="t", source="test", config=config
        )
        profile = profile_dataset(dataset, config=config)
        assert any(f.code == "INSUFFICIENT_EQUIPMENT" for f in profile.findings)

    def test_constant_channels_are_reported_but_not_fatal(self, config):
        frame = raw_frame(n_units=30, length=90, sensor_flat=7.0)
        dataset = build_dataset(frame, dataset_id="t", source="test", config=config)
        profile = profile_dataset(dataset, config=config)
        finding = next(f for f in profile.findings if f.code == "CONSTANT_CHANNELS")
        assert finding.severity == Severity.info
        assert "sensor_flat" in finding.detail["channels"]
        assert "sensor_flat" not in profile.varying_sensors

    def test_hours_based_time_is_flagged(self, config):
        frame = raw_frame(n_units=30, length=90).rename(columns={"time_in_cycles": "elapsed_hours"})
        dataset = build_dataset(frame, dataset_id="t", source="test", config=config)
        profile = profile_dataset(dataset, config=config)
        assert any(f.code == "HOURS_BASED_TIME" for f in profile.findings)

    def test_the_assumption_of_complete_histories_is_stated(self, dataset):
        profile = profile_dataset(dataset)
        assert any(f.code == "ASSUMED_COMPLETE_HISTORIES" for f in profile.findings)


class TestSplits:
    def test_partitions_are_disjoint_and_complete(self, splits, dataset):
        validate_splits(splits)
        assert len(splits.holdout) == 4
        assert set(splits.holdout) | set(splits.development) == set(dataset.equipment_ids)
        assert not set(splits.holdout) & set(splits.development)

    def test_every_development_engine_validates_exactly_once(self, splits):
        appearances = [engine for fold in splits.folds for engine in fold]
        assert sorted(appearances) == sorted(splits.development)

    def test_no_engine_trains_and_validates_in_the_same_fold(self, splits):
        for train, validation in fold_pairs(splits):
            assert not set(train) & set(validation)
            assert set(train) | set(validation) == set(splits.development)

    def test_splits_are_reproducible_for_the_same_data(self, dataset, config):
        assert make_splits(dataset, config) == make_splits(dataset, config)

    def test_too_few_engines_is_refused_rather_than_silently_shrunk(self, dataset, config):
        with pytest.raises(ValueError, match="cannot support"):
            make_splits(dataset, config, holdout_engines=200)
