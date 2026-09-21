"""Calibration assessment.

A score used as a threshold needs only to rank cycles correctly. A score
presented to an engineer as "a 70% chance of failure within 30 cycles" needs to be
calibrated, and the two are different properties. This module measures the second
so the interface can avoid claiming it when it does not hold, and so the effect of
sensor faults on calibration can be reported rather than assumed.
"""

from __future__ import annotations

import numpy as np

from app.schemas import (
    CalibrationReport,
    CandidateKind,
    Partition,
    ReliabilityBin,
)


def brier_score(labels: np.ndarray, scores: np.ndarray) -> float:
    """Mean squared difference between score and outcome. Lower is better."""
    labels = np.asarray(labels, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64)
    finite = np.isfinite(scores)
    if not finite.any():
        return float("nan")
    return float(np.mean(np.square(scores[finite] - labels[finite])))


def reliability_bins(
    labels: np.ndarray, scores: np.ndarray, n_bins: int = 10
) -> list[ReliabilityBin]:
    """Observed failure rate against mean predicted score, per score band.

    Empty bins are omitted rather than reported as zero, which would draw a
    reliability curve through points no data supports.
    """
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
    for bin_index in range(n_bins):
        members = indices == bin_index
        count = int(members.sum())
        if count == 0:
            continue
        bins.append(
            ReliabilityBin(
                lower=float(edges[bin_index]),
                upper=float(edges[bin_index + 1]),
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


def max_calibration_gap(report: CalibrationReport) -> float:
    """Largest gap between predicted and observed rate across populated bins."""
    if not report.bins:
        return float("nan")
    return max(abs(b.mean_predicted - b.observed_rate) for b in report.bins)
