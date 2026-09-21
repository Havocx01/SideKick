"""Feature construction.

"Causal features, no lookahead" is a claim the submission makes about its own
validity, so it is tested rather than asserted in a comment.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.features.build import FEATURES_PER_SENSOR, FeatureBuilder, assert_no_lookahead
from app.features.windows import rolling_mean, rolling_slope


class TestWindows:
    def test_rolling_mean_matches_definition(self):
        values = np.arange(1.0, 11.0)
        result = rolling_mean(values, 3)
        assert np.isnan(result[:2]).all(), "the first two cycles have no full window"
        assert result[2] == pytest.approx(2.0)
        assert result[-1] == pytest.approx(9.0)

    def test_rolling_slope_recovers_a_known_gradient(self):
        # A line with gradient 2.5 per cycle must produce a slope of 2.5.
        values = 2.5 * np.arange(20.0) + 7.0
        result = rolling_slope(values, 5)
        assert np.allclose(result[4:], 2.5)

    def test_rolling_slope_is_zero_on_a_flat_signal(self):
        result = rolling_slope(np.full(15, 3.3), 5)
        assert np.allclose(result[4:], 0.0)

    def test_short_history_returns_all_nan(self):
        assert np.isnan(rolling_mean(np.arange(3.0), 10)).all()
        assert np.isnan(rolling_slope(np.arange(3.0), 10)).all()


class TestFeatureBuilder:
    def test_layout_is_contiguous_per_sensor(self, builder):
        names = builder.feature_names()
        assert len(names) == builder.n_features
        assert builder.n_features == len(builder.sensors) * FEATURES_PER_SENSOR
        for sensor in builder.sensors:
            block = names[builder.block(sensor)]
            assert len(block) == FEATURES_PER_SENSOR
            assert all(name.startswith(f"{sensor}__") for name in block)

    def test_no_feature_depends_on_a_future_reading(self, builder, dataset):
        assert_no_lookahead(builder, dataset)

    def test_perturbing_one_cycle_leaves_earlier_cycles_untouched(self, builder, dataset):
        readings = dataset.sensor_matrix(dataset.equipment_ids[0])
        baseline = builder.build_engine(readings)

        position = 40
        tampered = readings.copy()
        tampered[position, :] += 500.0
        after = builder.build_engine(tampered)

        assert np.allclose(baseline[:position], after[:position], equal_nan=True)
        assert not np.allclose(baseline[position], after[position], equal_nan=True)

    def test_warmup_rows_are_not_finite(self, builder, dataset):
        features = builder.build_engine(dataset.sensor_matrix(dataset.equipment_ids[0]))
        warmup = builder.window - 1
        # Trailing statistics are undefined during warm-up and must not be guessed.
        assert not np.isfinite(features[: warmup, 1]).any()
        assert np.isfinite(features[warmup:]).all()

    def test_rebuild_touches_only_the_named_sensor(self, builder, dataset):
        readings = dataset.sensor_matrix(dataset.equipment_ids[1])
        baseline = builder.build_engine(readings)

        sensor = builder.sensors[2]
        corrupted = readings[:, builder.preprocessor.index_of(sensor)] * 1.5 + 10.0
        rebuilt = builder.rebuild_sensor(baseline.copy(), corrupted, sensor)

        target = builder.block(sensor)
        changed = ~np.isclose(baseline, rebuilt, equal_nan=True)
        touched_columns = set(np.flatnonzero(changed.any(axis=0)))
        assert touched_columns <= set(range(target.start, target.stop))
        assert touched_columns, "the rebuild should have changed that sensor's columns"

    def test_rebuild_equals_a_full_rebuild(self, builder, dataset):
        """The cheap path must give the same answer as recomputing everything."""
        readings = dataset.sensor_matrix(dataset.equipment_ids[2])
        sensor = builder.sensors[1]
        index = builder.preprocessor.index_of(sensor)

        corrupted_column = readings[:, index].copy()
        corrupted_column[60:] = np.nan

        full_input = readings.copy()
        full_input[:, index] = corrupted_column
        expected = builder.build_engine(full_input)

        cheap = builder.rebuild_sensor(
            builder.build_engine(readings).copy(), corrupted_column, sensor
        )
        assert np.allclose(expected, cheap, equal_nan=True)

    def test_missing_readings_are_imputed_and_flagged(self, builder, dataset):
        readings = dataset.sensor_matrix(dataset.equipment_ids[0])
        sensor = builder.sensors[0]
        index = builder.preprocessor.index_of(sensor)

        column = readings[:, index].copy()
        column[50:] = np.nan
        features = builder.rebuild_sensor(builder.build_engine(readings).copy(), column, sensor)

        block = builder.block(sensor)
        values = features[:, block.start]
        flags = features[:, block.start + 3]

        assert np.isfinite(values[50:]).all(), "missing readings must be imputed, not left NaN"
        assert values[60] == builder.preprocessor.medians[index]
        # The flag is a trailing fraction, so it saturates once the window is inside the gap.
        assert flags[50 + builder.window] == 1.0
        assert flags[40] == 0.0

    def test_builder_rejects_the_wrong_channel_count(self, builder):
        with pytest.raises(ValueError, match="channels"):
            builder.build_engine(np.zeros((20, 2)))


class TestPreprocessor:
    def test_statistics_come_only_from_the_selected_rows(self, dataset, config):
        from app.features.build import Preprocessor

        everything = Preprocessor.fit(dataset)
        subset_rows = dataset.frame["equipment_id"].isin(dataset.equipment_ids[:3]).to_numpy()
        subset = Preprocessor.fit(dataset, subset_rows)

        assert not np.allclose(everything.medians, subset.medians), (
            "fitting on a subset must not reproduce the full-data statistics, "
            "otherwise per-fold preprocessing is not actually isolated"
        )

    def test_empty_selection_is_rejected(self, dataset):
        from app.features.build import Preprocessor

        with pytest.raises(ValueError, match="empty"):
            Preprocessor.fit(dataset, np.zeros(len(dataset.frame), dtype=bool))

    def test_constant_channels_have_zero_standard_deviation(self, preprocessor):
        assert preprocessor.std_of("rated_voltage") == 0.0
