"""The four candidates."""

from __future__ import annotations

import os

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.models.base import Candidate, DesignMatrix
from app.schemas import CandidateKind
from app.utils.determinism import derive_seed


class LogisticRegressionCandidate(Candidate):
    kind = CandidateKind.logistic_regression

    def describe(self) -> str:
        return f"Standardised logistic regression, C={self.params.get('C', 1.0)}"

    def fit(self, train: DesignMatrix, *, augmented: DesignMatrix | None = None) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        train.assert_finite()
        self._pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=float(self.params.get("C", 1.0)),
                        max_iter=int(self.params.get("max_iter", 2000)),
                        class_weight=self.params.get("class_weight", "balanced"),
                        solver="lbfgs",
                    ),
                ),
            ]
        )
        self._pipeline.fit(train.X, train.y)
        self._feature_names = list(train.feature_names)
        self._fitted = True

    def score(self, data: DesignMatrix) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError(f"{self.name} has not been fitted")
        return self._pipeline.predict_proba(data.X)[:, 1]

    def feature_importance(self) -> dict[str, float] | None:
        if not self._fitted:
            return None
        coefficients = self._pipeline.named_steps["model"].coef_[0]
        return {name: float(abs(value)) for name, value in zip(self._feature_names, coefficients, strict=True)}


class XGBoostCandidate(Candidate):
    kind = CandidateKind.xgboost

    def describe(self) -> str:
        return f"XGBoost, depth={self.params.get('max_depth', 4)}, trees={self.params.get('n_estimators', 300)}"

    def _make_model(self, seed: int):
        from xgboost import XGBClassifier

        return XGBClassifier(
            max_depth=int(self.params.get("max_depth", 4)),
            n_estimators=int(self.params.get("n_estimators", 300)),
            learning_rate=float(self.params.get("learning_rate", 0.05)),
            subsample=float(self.params.get("subsample", 0.9)),
            colsample_bytree=float(self.params.get("colsample_bytree", 0.9)),
            min_child_weight=float(self.params.get("min_child_weight", 5.0)),
            reg_lambda=float(self.params.get("reg_lambda", 1.0)),
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            n_jobs=min(int(self.params.get("n_jobs", 4)), max(1, int(os.environ.get("SIDEKICK_TRAIN_THREADS", "4")))),
            random_state=seed,
            verbosity=0,
        )

    def fit(self, train: DesignMatrix, *, augmented: DesignMatrix | None = None) -> None:
        seed = int(self.params.get("model_seed", derive_seed(EXPERIMENT.base_seed, self.kind.value, self.config_id)))
        self._model = self._make_model(seed)
        self._model.fit(train.X, train.y)
        self._feature_names = list(train.feature_names)
        self._fitted = True

    def score(self, data: DesignMatrix) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError(f"{self.name} has not been fitted")
        return self._model.predict_proba(data.X)[:, 1]

    def feature_importance(self) -> dict[str, float] | None:
        if not self._fitted:
            return None
        scores = self._model.feature_importances_
        return {name: float(value) for name, value in zip(self._feature_names, scores, strict=True)}

    @property
    def booster(self):
        return self._model if self._fitted else None


class AugmentedXGBoostCandidate(XGBoostCandidate):
    """Sensor faults change the inputs, never the failure labels."""

    kind = CandidateKind.xgboost_augmented
    requires_augmentation = True

    def describe(self) -> str:
        return f"{super().describe()}, trained with injected sensor faults"

    def fit(self, train: DesignMatrix, *, augmented: DesignMatrix | None = None) -> None:
        if augmented is None or len(augmented) == 0:
            # Without corrupted copies, this would duplicate the unaugmented candidate.
            raise ValueError(f"{self.name} requires augmented training rows; none were supplied")
        combined = DesignMatrix(
            X=np.vstack([train.X, augmented.X]),
            y=np.concatenate([train.y, augmented.y]),
            cycle=np.concatenate([train.cycle, augmented.cycle]),
            equipment_id=np.concatenate([train.equipment_id, augmented.equipment_id]),
            rul=np.concatenate([train.rul, augmented.rul]),
            rows=np.concatenate([train.rows, augmented.rows]),
            feature_names=train.feature_names,
        )
        super().fit(combined)
        self.params["augmented_rows"] = len(augmented)


class AgeBaselineCandidate(Candidate):
    kind = CandidateKind.age_baseline
    uses_sensors = False

    def describe(self) -> str:
        return "Alerts on running time alone; immune to sensor faults by construction"

    def fit(self, train: DesignMatrix, *, augmented: DesignMatrix | None = None) -> None:
        # The common threshold-selection step calibrates this running-time baseline.
        self._fitted = True

    def score(self, data: DesignMatrix) -> np.ndarray:
        return data.cycle.astype(np.float64)


def candidate_grid(config: ExperimentConfig = EXPERIMENT) -> list[Candidate]:
    limit = config.configs_per_candidate

    logisticParams = [{"C": 0.05}, {"C": 0.5}, {"C": 5.0}][:limit]
    treeParams = [
        {"max_depth": 3, "n_estimators": 250, "learning_rate": 0.05},
        {"max_depth": 5, "n_estimators": 400, "learning_rate": 0.05},
        {"max_depth": 7, "n_estimators": 250, "learning_rate": 0.1},
    ][:limit]

    candidates: list[Candidate] = []
    for index, params in enumerate(logisticParams, start=1):
        candidates.append(LogisticRegressionCandidate(f"lr{index}", params))
    for index, params in enumerate(treeParams, start=1):
        candidates.append(XGBoostCandidate(f"xgb{index}", params))
    for index, params in enumerate(treeParams, start=1):
        candidates.append(AugmentedXGBoostCandidate(f"aug{index}", params))
    candidates.append(AgeBaselineCandidate("age1"))
    return candidates


def rebuild_candidate(kind: CandidateKind, config_id: str, params: dict) -> Candidate:
    registry = {
        CandidateKind.logistic_regression: LogisticRegressionCandidate,
        CandidateKind.xgboost: XGBoostCandidate,
        CandidateKind.xgboost_augmented: AugmentedXGBoostCandidate,
        CandidateKind.age_baseline: AgeBaselineCandidate,
    }
    return registry[kind](config_id, params)
