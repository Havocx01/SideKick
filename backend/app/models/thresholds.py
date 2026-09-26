"""Alert threshold selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.schemas import AcceptanceCriteria, AlertMetrics

# Quantiles also work for the age baseline, whose scores are cycle counts.
DEFAULT_GRID = 40


@dataclass
class ThresholdChoice:
    threshold: float
    metrics: AlertMetrics
    within_budget: bool
    considered: int
    note: str | None = None


def candidate_thresholds(scores: np.ndarray, grid: int = DEFAULT_GRID) -> np.ndarray:
    finite = np.asarray(scores, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.array([0.5])
    quantiles = np.linspace(0.01, 0.999, grid)
    values = np.unique(np.quantile(finite, quantiles))
    # Include a threshold above the maximum so "never alert" stays reachable.
    return np.append(values, np.nextafter(finite.max(), np.inf))


def choose_threshold(
    scores: np.ndarray,
    evaluate: Callable[[float], AlertMetrics],
    criteria: AcceptanceCriteria,
    *,
    grid: int = DEFAULT_GRID,
) -> ThresholdChoice:
    thresholds = candidate_thresholds(scores, grid)
    results = [(float(t), evaluate(float(t))) for t in thresholds]

    within = [(t, m) for t, m in results if m.early_alarm_burden <= criteria.max_early_alarm_burden]
    if within:
        threshold, metrics = max(within, key=lambda pair: (pair[1].detection_fraction, -pair[1].early_alarm_burden))
        return ThresholdChoice(threshold=threshold, metrics=metrics, within_budget=True, considered=len(results))

    threshold, metrics = min(results, key=lambda pair: pair[1].early_alarm_burden)
    return ThresholdChoice(
        threshold=threshold,
        metrics=metrics,
        within_budget=False,
        considered=len(results),
        note=(
            "No threshold kept the early alarm burden inside the budget of "
            f"{criteria.max_early_alarm_burden:.1%}; the lowest achievable burden was "
            f"{metrics.early_alarm_burden:.1%}."
        ),
    )
