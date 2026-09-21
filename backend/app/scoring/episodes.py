"""Alert episode logic.

A single score crossing a threshold is not an alert. An alert opens after two
consecutive scores reach the threshold and closes after two consecutive scores
fall below it, which is what keeps a noisy score from producing a burst of
one-cycle alarms.

The episode is timed from the cycle where the alert actually fires, meaning the
second of the two qualifying scores. Timing it from the first would credit the
model with a warning that had not yet been raised.
"""

from __future__ import annotations

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import AlertEpisode


def alert_state(
    scores: np.ndarray,
    threshold: float,
    *,
    on_consecutive: int = 2,
    off_consecutive: int = 2,
    valid: np.ndarray | None = None,
) -> np.ndarray:
    """Per-cycle boolean: is an alert active?

    ``valid`` marks cycles that carry a score at all. Invalid cycles, such as the
    warm-up period, neither open nor close an episode; the run of consecutive
    observations simply pauses.
    """
    scores = np.asarray(scores, dtype=np.float64)
    active = np.zeros(scores.shape[0], dtype=bool)
    if scores.size == 0:
        return active
    if valid is None:
        valid = np.isfinite(scores)
    else:
        valid = np.asarray(valid, dtype=bool) & np.isfinite(scores)

    is_on = False
    run_high = 0
    run_low = 0
    for index in range(scores.shape[0]):
        if not valid[index]:
            active[index] = is_on
            continue
        if scores[index] >= threshold:
            run_high += 1
            run_low = 0
        else:
            run_low += 1
            run_high = 0
        if not is_on and run_high >= on_consecutive:
            is_on = True
        elif is_on and run_low >= off_consecutive:
            is_on = False
        active[index] = is_on
    return active


def episodes_from_state(
    active: np.ndarray, cycles: np.ndarray, rul: np.ndarray
) -> list[AlertEpisode]:
    """Convert a per-cycle active flag into contiguous episodes."""
    active = np.asarray(active, dtype=bool)
    if not active.any():
        return []
    cycles = np.asarray(cycles, dtype=int)
    rul = np.asarray(rul, dtype=int)

    padded = np.concatenate(([False], active, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts, stops = edges[0::2], edges[1::2]

    episodes: list[AlertEpisode] = []
    for start, stop in zip(starts, stops, strict=True):
        last = stop - 1
        episodes.append(
            AlertEpisode(
                start_cycle=int(cycles[start]),
                end_cycle=int(cycles[last]),
                start_rul=int(rul[start]),
                end_rul=int(rul[last]),
                still_open_at_failure=bool(stop == active.shape[0]),
            )
        )
    return episodes


def detect_episodes(
    scores: np.ndarray,
    cycles: np.ndarray,
    rul: np.ndarray,
    threshold: float,
    *,
    config: ExperimentConfig = EXPERIMENT,
    valid: np.ndarray | None = None,
) -> tuple[np.ndarray, list[AlertEpisode]]:
    """Alert state and episodes for one engine."""
    active = alert_state(
        scores,
        threshold,
        on_consecutive=config.alert_on_consecutive,
        off_consecutive=config.alert_off_consecutive,
        valid=valid,
    )
    return active, episodes_from_state(active, cycles, rul)
