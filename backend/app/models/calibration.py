"""Calibration assessment."""

from __future__ import annotations

import numpy as np

from app.schemas import CalibrationReport, CandidateKind, Partition, ReliabilityBin


def brier_score(labels: np.ndarray, scores: np.ndarray) -> float:
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    finite = np.isfinite(scores)
    if not finite.any():
        return float("nan")
    return float(np.mean(np.square(scores[finite] - labels[finite])))


def reliability_bins(labels: np.ndarray, scores: np.ndarray, n_bins: int = 10) -> list[ReliabilityBin]:
    """Omit empty bins; they provide no observed event rate."""
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    finite = np.isfinite(scores)
    labels, scores = labels[finite], scores[finite]
    if scores.size == 0:
        return []

    lowest, highest = float(scores.min()), float(scores.max())
    if highest <= lowest:
        return [
            ReliabilityBin(
                lower=lowest,
                upper=highest,
                count=int(scores.size),
                mean_predicted=lowest,
                observed_rate=float(labels.mean()),
            )
        ]

    edges = np.linspace(lowest, highest, n_bins + 1)
    indices = np.clip(np.digitize(scores, edges[1:-1], right=False), 0, n_bins - 1)

    bins: list[ReliabilityBin] = []
    for binIndex in range(n_bins):
        members = indices == binIndex
        count = int(members.sum())
        if count == 0:
            continue
        bins.append(
            ReliabilityBin(
                lower=float(edges[binIndex]),
                upper=float(edges[binIndex + 1]),
                count=count,
                mean_predicted=float(scores[members].mean()),
                observed_rate=float(labels[members].mean()),
            )
        )
    return bins


def calibration_report(
    *,
    candidate: CandidateKind,
    config_id: str,
    labels: np.ndarray,
    scores: np.ndarray,
    partition: Partition = Partition.out_of_fold,
    n_bins: int = 10,
) -> CalibrationReport:
    return CalibrationReport(
        candidate=candidate,
        config_id=config_id,
        partition=partition,
        brier=brier_score(labels, scores),
        bins=reliability_bins(labels, scores, n_bins),
    )
