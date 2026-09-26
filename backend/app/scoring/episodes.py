"""Alert episode logic."""

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
    """Invalid cycles leave both pending streaks and the current alert state unchanged."""
    scores = np.asarray(scores, dtype=np.float64)
    active = np.zeros(scores.shape[0], dtype=bool)
    if scores.size == 0:
        return active
    if valid is None:
        valid = np.isfinite(scores)
    else:
        valid = np.asarray(valid, dtype=bool) & np.isfinite(scores)

    isOn = False
    runHigh = 0
    runLow = 0
    for index in range(scores.shape[0]):
        if not valid[index]:
            active[index] = isOn
            continue
        if scores[index] >= threshold:
            runHigh += 1
            runLow = 0
        else:
            runLow += 1
            runHigh = 0
        if not isOn and runHigh >= on_consecutive:
            isOn = True
        elif isOn and runLow >= off_consecutive:
            isOn = False
        active[index] = isOn
    return active


def episodes_from_state(
    active: np.ndarray, cycles: np.ndarray, rul: np.ndarray, scores: np.ndarray | None = None
) -> list[AlertEpisode]:
    active = np.asarray(active, dtype=bool)
    if not active.any():
        return []
    cycles = np.asarray(cycles, dtype=int)
    rul = np.asarray(rul, dtype=int)
    values = None if scores is None else np.asarray(scores, dtype=np.float64)

    padded = np.concatenate(([False], active, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts, stops = edges[0::2], edges[1::2]

    episodes: list[AlertEpisode] = []
    for start, stop in zip(starts, stops, strict=True):
        last = stop - 1
        peak = None
        if values is not None:
            window = values[start:stop]
            finite = window[np.isfinite(window)]
            peak = float(finite.max()) if finite.size else None
        episodes.append(
            AlertEpisode(
                start_cycle=int(cycles[start]),
                end_cycle=int(cycles[last]),
                start_rul=int(rul[start]),
                end_rul=int(rul[last]),
                still_open_at_failure=bool(stop == active.shape[0]),
                peak_score=peak,
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
    active = alert_state(
        scores,
        threshold,
        on_consecutive=config.alert_on_consecutive,
        off_consecutive=config.alert_off_consecutive,
        valid=valid,
    )
    return active, episodes_from_state(active, cycles, rul, scores)
