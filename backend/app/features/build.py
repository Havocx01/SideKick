"""Causal feature construction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.features.windows import rolling_mean, rolling_slope

FEATURE_KINDS = ("value", "trailing_mean", "trailing_slope", "missing_fraction")
FEATURES_PER_SENSOR = len(FEATURE_KINDS)


@dataclass(frozen=True)
class Preprocessor:
    """Training-only statistics, reused unchanged when rebuilding faulted features."""

    sensors: tuple[str, ...]
    medians: np.ndarray
    stds: np.ndarray

    @classmethod
    def fit(cls, dataset: Dataset, rows: np.ndarray | None = None) -> Preprocessor:
        mask = dataset.scorable_mask() if rows is None else np.asarray(rows, dtype=bool)
        if not mask.any():
            raise ValueError("cannot fit preprocessing on an empty row selection")
        values = dataset.frame.loc[mask, dataset.sensors].to_numpy(dtype=np.float64)
        medians = np.nanmedian(values, axis=0)
        # Missing-only channels use zero; the missingness feature retains the gap.
        medians = np.where(np.isfinite(medians), medians, 0.0)
        stds = np.nanstd(values, axis=0, ddof=0)
        stds = np.where(np.isfinite(stds), stds, 0.0)
        return cls(sensors=tuple(dataset.sensors), medians=medians, stds=stds)

    def index_of(self, sensor: str) -> int:
        try:
            return self.sensors.index(sensor)
        except ValueError as exc:
            raise KeyError(f"unknown sensor {sensor!r}") from exc

    def std_of(self, sensor: str) -> float:
        return float(self.stds[self.index_of(sensor)])


class FeatureBuilder:
    def __init__(self, preprocessor: Preprocessor, config: ExperimentConfig = EXPERIMENT) -> None:
        self.preprocessor = preprocessor
        self.config = config
        self.window = config.feature_window
        self.sensors = list(preprocessor.sensors)

    @property
    def n_features(self) -> int:
        return len(self.sensors) * FEATURES_PER_SENSOR

    def feature_names(self) -> list[str]:
        return [f"{sensor}__{kind}" for sensor in self.sensors for kind in FEATURE_KINDS]

    def block(self, sensor: str) -> slice:
        start = self.preprocessor.index_of(sensor) * FEATURES_PER_SENSOR
        return slice(start, start + FEATURES_PER_SENSOR)

    def build_engine(self, raw: np.ndarray) -> np.ndarray:
        raw = np.asarray(raw, dtype=np.float64)
        if raw.ndim != 2 or raw.shape[1] != len(self.sensors):
            raise ValueError(f"expected readings with {len(self.sensors)} channels, got {raw.shape}")
        out = np.empty((raw.shape[0], self.n_features), dtype=np.float64)
        for index in range(len(self.sensors)):
            self._fill_block(out, raw[:, index], index)
        return out

    def rebuild_sensor(self, features: np.ndarray, column: np.ndarray, sensor: str) -> np.ndarray:
        """Update a copy of the clean feature matrix for the same equipment."""
        self._fill_block(features, np.asarray(column, dtype=np.float64), self.preprocessor.index_of(sensor))
        return features

    def _fill_block(self, out: np.ndarray, column: np.ndarray, index: int) -> None:
        missing = ~np.isfinite(column)
        # Impute before windowing so missing readings do not propagate through trailing statistics.
        filled = np.where(missing, self.preprocessor.medians[index], column)
        base = index * FEATURES_PER_SENSOR
        out[:, base + 0] = filled
        out[:, base + 1] = rolling_mean(filled, self.window)
        out[:, base + 2] = rolling_slope(filled, self.window)
        out[:, base + 3] = rolling_mean(missing.astype(np.float64), self.window)

    def build_dataset(self, dataset: Dataset) -> np.ndarray:
        """The last reading is a failure target only when the caller confirms complete histories."""
        out = np.empty((len(dataset.frame), self.n_features), dtype=np.float64)
        for equipmentId in dataset.equipment_ids:
            start, stop = dataset.rows_for(equipmentId)
            out[start:stop, :] = self.build_engine(dataset.sensor_matrix(equipmentId))
        return out


def assert_no_lookahead(builder: FeatureBuilder, dataset: Dataset) -> None:
    equipmentId = dataset.equipment_ids[0]
    readings = dataset.sensor_matrix(equipmentId)
    if readings.shape[0] < 2:
        return
    baseline = builder.build_engine(readings)

    tampered = readings.copy()
    tampered[-1, :] += 1_000.0
    after = builder.build_engine(tampered)

    if not np.allclose(baseline[:-1], after[:-1], equal_nan=True):
        raise AssertionError("a feature at an earlier cycle changed with a future reading")
