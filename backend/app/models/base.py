"""The candidate interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from app.schemas import CandidateConfig, CandidateKind


@dataclass
class DesignMatrix:
    """Sensor features exclude equipment ID, cycle count and remaining life."""

    X: np.ndarray
    y: np.ndarray
    cycle: np.ndarray
    equipment_id: np.ndarray
    rul: np.ndarray
    rows: np.ndarray
    feature_names: list[str]

    def __post_init__(self) -> None:
        lengths = {len(self.X), len(self.y), len(self.cycle), len(self.equipment_id), len(self.rul), len(self.rows)}
        if len(lengths) != 1:
            raise ValueError(f"design matrix components disagree on length: {lengths}")
        if self.X.shape[1] != len(self.feature_names):
            raise ValueError("feature name count does not match the matrix width")

    def __len__(self) -> int:
        return len(self.y)

    def select(self, mask: np.ndarray) -> DesignMatrix:
        mask = np.asarray(mask)
        return DesignMatrix(
            X=self.X[mask],
            y=self.y[mask],
            cycle=self.cycle[mask],
            equipment_id=self.equipment_id[mask],
            rul=self.rul[mask],
            rows=self.rows[mask],
            feature_names=self.feature_names,
        )

    def assert_finite(self) -> None:
        if not np.isfinite(self.X).all():
            bad = int((~np.isfinite(self.X)).sum())
            raise ValueError(
                f"{bad} non-finite feature values reached the estimator; the "
                "scorable mask should have removed warm-up rows"
            )


class Candidate(ABC):
    kind: CandidateKind
    uses_sensors: bool = True
    requires_augmentation: bool = False

    def __init__(self, config_id: str, params: dict | None = None) -> None:
        self.config_id = config_id
        self.params = dict(params or {})
        self._fitted = False

    @property
    def name(self) -> str:
        return f"{self.kind.value}/{self.config_id}"

    def spec(self) -> CandidateConfig:
        return CandidateConfig(
            candidate=self.kind,
            config_id=self.config_id,
            params=self.params,
            uses_sensors=self.uses_sensors,
            description=self.describe(),
        )

    def describe(self) -> str:
        return ""

    @abstractmethod
    def fit(self, train: DesignMatrix, *, augmented: DesignMatrix | None = None) -> None:
        pass

    @abstractmethod
    def score(self, data: DesignMatrix) -> np.ndarray:
        """Higher scores indicate greater risk inside the prediction horizon."""

    @property
    def fitted(self) -> bool:
        return self._fitted

    def feature_importance(self) -> dict[str, float] | None:
        return None
