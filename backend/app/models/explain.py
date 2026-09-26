"""Per-alert attributions."""

from __future__ import annotations

import numpy as np

from app.models.base import Candidate, DesignMatrix
from app.schemas import AlertExplanation, CandidateKind, ShapContribution

DEFAULT_TOP_K = 8


def _top_contributions(
    feature_names: list[str], values: np.ndarray, contributions: np.ndarray, top_k: int
) -> list[ShapContribution]:
    order = np.argsort(-np.abs(contributions))[:top_k]
    return [
        ShapContribution(
            feature=feature_names[index],
            value=float(values[index]) if np.isfinite(values[index]) else None,
            contribution=float(contributions[index]),
        )
        for index in order
    ]


def explain_alert(
    candidate: Candidate, design: DesignMatrix, position: int, *, top_k: int = DEFAULT_TOP_K
) -> AlertExplanation:
    equipmentId = str(design.equipment_id[position])
    cycle = int(design.cycle[position])
    score = float(candidate.score(design.select(np.array([position])))[0])
    row = design.X[position]

    if candidate.kind == CandidateKind.age_baseline:
        return AlertExplanation(
            equipment_id=equipmentId,
            cycle=cycle,
            score=score,
            base_value=0.0,
            contributions=[
                ShapContribution(feature="running_time_cycles", value=float(cycle), contribution=float(cycle))
            ],
            available=True,
            note=("This candidate reads no sensor. Its score is running time, so there is nothing else to attribute."),
        )

    if candidate.kind == CandidateKind.logistic_regression:
        pipeline = getattr(candidate, "_pipeline", None)
        if pipeline is None:
            return _unavailable(equipmentId, cycle, score, "the model is not fitted")
        scaler = pipeline.named_steps["scale"]
        model = pipeline.named_steps["model"]
        standardised = (row - scaler.mean_) / np.where(scaler.scale_ == 0, 1.0, scaler.scale_)
        contributions = model.coef_[0] * standardised
        return AlertExplanation(
            equipment_id=equipmentId,
            cycle=cycle,
            score=score,
            base_value=float(model.intercept_[0]),
            contributions=_top_contributions(design.feature_names, row, contributions, top_k),
            available=True,
            note=(
                "Exact linear attribution in log-odds: coefficient times standardised "
                "feature value. Describes model behaviour, not physical cause."
            ),
        )

    booster = getattr(candidate, "booster", None)
    if booster is None:
        return _unavailable(equipmentId, cycle, score, "the model is not fitted")

    try:
        import xgboost as xgb

        matrix = xgb.DMatrix(row.reshape(1, -1), feature_names=None)
        contributions = booster.get_booster().predict(matrix, pred_contribs=True)[0]
    except Exception as exc:  # pragma: no cover - depends on the installed build
        return _unavailable(equipmentId, cycle, score, f"attribution failed: {exc}")

    # The final column is the model bias, not a feature.
    baseValue = float(contributions[-1])
    featureContributions = np.asarray(contributions[:-1], dtype=np.float64)
    return AlertExplanation(
        equipment_id=equipmentId,
        cycle=cycle,
        score=score,
        base_value=baseValue,
        contributions=_top_contributions(design.feature_names, row, featureContributions, top_k),
        available=True,
        note=(
            "Exact tree SHAP values in log-odds, from XGBoost's own contribution "
            "computation. Describes model behaviour, not physical cause."
        ),
    )


def _unavailable(equipment_id: str, cycle: int, score: float, reason: str) -> AlertExplanation:
    return AlertExplanation(
        equipment_id=equipment_id,
        cycle=cycle,
        score=score,
        contributions=[],
        available=False,
        note=f"No attribution available: {reason}.",
    )


def global_importance(candidate: Candidate, top_k: int = 15) -> dict[str, float]:
    importance = candidate.feature_importance() or {}
    ranked = sorted(importance.items(), key=lambda item: -item[1])[:top_k]
    return dict(ranked)
