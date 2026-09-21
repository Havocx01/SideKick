"""Causal feature construction.

Three properties matter and are enforced here rather than left to convention:

**No lookahead.** Every feature at cycle *t* is a function of cycles
``t - window + 1 .. t`` only. Equipment identity, cycle count and remaining life
are excluded from the design matrix; age dependence is measured explicitly by the
separate age baseline instead of leaking in as a feature.

**Frozen preprocessing.** Imputation medians and the per-sensor standard
deviations used to scale drift severity are fitted on training rows only, then
reused unchanged when features are rebuilt from a corrupted signal.

**Cheap rebuilds.** A fault touches exactly one sensor, so features are laid out
in contiguous per-sensor blocks and :meth:`FeatureBuilder.rebuild_sensor`
recomputes only that sensor's four columns against a cached clean matrix. This is
what keeps the fault matrix inside its runtime budget.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.features.windows import rolling_mean, rolling_slope

#: Feature kinds emitted per sensor, in block order.
FEATURE_KINDS = ("value", "trailing_mean", "trailing_slope", "missing_fraction")
FEATURES_PER_SENSOR = len(FEATURE_KINDS)


@dataclass(frozen=True)
class Preprocessor:
    """Statistics fitted on training rows and then frozen.

    ``medians`` fill missing readings. ``stds`` express drift severity in
    training standard deviations, so a "1 SD drift" means the same thing across
    every scenario regardless of which rows were corrupted.
    """

    sensors: tuple[str, ...]
    medians: np.ndarray
    stds: np.ndarray

    @classmethod
    def fit(cls, dataset: Dataset, rows: np.ndarray | None = None) -> Preprocessor:
        """Fit on the given boolean row mask, defaulting to every scorable row."""
        mask = dataset.scorable_mask() if rows is None else np.asarray(rows, dtype=bool)
        if not mask.any():
            raise ValueError("cannot fit preprocessing on an empty row selection")
        values = dataset.frame.loc[mask, dataset.sensors].to_numpy(dtype=np.float64)
        medians = np.nanmedian(values, axis=0)
        # A channel that is entirely missing in training has no median; zero is a
        # neutral fill and the missingness flag still records the absence.
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
    """Builds the design matrix for one dataset under one preprocessor."""

    def __init__(
        self,
        preprocessor: Preprocessor,
        config: ExperimentConfig = EXPERIMENT,
    ) -> None:
        self.preprocessor = preprocessor
        self.config = config
        self.window = config.feature_window
        self.sensors = list(preprocessor.sensors)

    # -- layout ------------------------------------------------------------

    @property
    def n_features(self) -> int:
        return len(self.sensors) * FEATURES_PER_SENSOR

    def feature_names(self) -> list[str]:
        return [f"{sensor}__{kind}" for sensor in self.sensors for kind in FEATURE_KINDS]

    def block(self, sensor: str) -> slice:
        """Column slice occupied by one sensor."""
        start = self.preprocessor.index_of(sensor) * FEATURES_PER_SENSOR
        return slice(start, start + FEATURES_PER_SENSOR)

    # -- construction ------------------------------------------------------

    def build_engine(self, raw: np.ndarray) -> np.ndarray:
        """Features for one engine from its ``(n_cycles, n_sensors)`` readings."""
        raw = np.asarray(raw, dtype=np.float64)
        if raw.ndim != 2 or raw.shape[1] != len(self.sensors):
            raise ValueError(
                f"expected readings with {len(self.sensors)} channels, got {raw.shape}"
            )
        out = np.empty((raw.shape[0], self.n_features), dtype=np.float64)
        for index in range(len(self.sensors)):
            self._fill_block(out, raw[:, index], index)
        return out

    def rebuild_sensor(
        self, features: np.ndarray, column: np.ndarray, sensor: str
    ) -> np.ndarray:
        """Recompute one sensor's block in place from a corrupted reading series.

        ``features`` must be a copy of the clean matrix for the same engine; the
        other sensors' columns are left untouched, which is the whole point.
        """
        self._fill_block(features, np.asarray(column, dtype=np.float64), self.preprocessor.index_of(sensor))
        return features

    def _fill_block(self, out: np.ndarray, column: np.ndarray, index: int) -> None:
        missing = ~np.isfinite(column)
        # Imputation happens before windowing, so a dropped-out sensor reads a
        # plausible training median rather than propagating NaN through the
        # trailing statistics. The missingness fraction records that it happened.
        filled = np.where(missing, self.preprocessor.medians[index], column)
        base = index * FEATURES_PER_SENSOR
        out[:, base + 0] = filled
        out[:, base + 1] = rolling_mean(filled, self.window)
        out[:, base + 2] = rolling_slope(filled, self.window)
        out[:, base + 3] = rolling_mean(missing.astype(np.float64), self.window)

    # -- dataset level -----------------------------------------------------

    def build_dataset(self, dataset: Dataset) -> np.ndarray:
        """Full design matrix, row-aligned with ``dataset.frame``."""
        out = np.empty((len(dataset.frame), self.n_features), dtype=np.float64)
        for equipment_id in dataset.equipment_ids:
            start, stop = dataset.rows_for(equipment_id)
            out[start:stop, :] = self.build_engine(dataset.sensor_matrix(equipment_id))
        return out

    def build_engine_cache(self, dataset: Dataset) -> dict[str, np.ndarray]:
        """Per-engine clean feature matrices, reused by every fault scenario."""
        return {
            equipment_id: self.build_engine(dataset.sensor_matrix(equipment_id))
            for equipment_id in dataset.equipment_ids
        }


def assert_no_lookahead(builder: FeatureBuilder, dataset: Dataset) -> None:
    """Verify empirically that no feature depends on a future reading.

    Perturbing the last cycle of a history must leave every earlier row
    unchanged. This is asserted in the test suite because "causal features" is a
    claim the submission makes, and a claim that is only enforced by comment
    tends to stop being true.
    """
    equipment_id = dataset.equipment_ids[0]
    readings = dataset.sensor_matrix(equipment_id)
    if readings.shape[0] < 2:
        return
    baseline = builder.build_engine(readings)

    tampered = readings.copy()
    tampered[-1, :] += 1_000.0
    after = builder.build_engine(tampered)

    if not np.allclose(baseline[:-1], after[:-1], equal_nan=True):
        raise AssertionError("a feature at an earlier cycle changed with a future reading")
