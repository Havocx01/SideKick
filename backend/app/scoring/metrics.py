"""Operational measures.

The definitions, all counted in operating cycles:

**Useful detection.** An alert is active at some cycle between ``horizon`` and
``min_useful_lead`` cycles before failure. Counted per engine, never per cycle.

**Late warning.** No alert in the useful window, but one appears inside the final
``late_window_end`` cycles. Reported separately from a miss, because a warning
that arrives too late to act on is a different failure from no warning at all.

**Missed.** Neither of the above.

**Early alarm burden.** Fraction of eligible cycles spent in alarm, where
eligible means more than ``transition_band_end`` cycles remain. Cycles 31 to 45
form a transition band excluded from the denominator, so an alert that opens
slightly before the horizon and stays open is not punished as a false alarm while
still counting as a detection. A permanently active alarm scores a burden of 1.0,
which is how a model that alerts on everything is caught.

**Warning lead time.** Cycles from the start of the first episode overlapping the
useful window to failure. An episode that opened earlier keeps its earlier start,
so lead time can exceed the horizon.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import AlertEpisode, AlertMetrics, EngineOutcome
from app.scoring.episodes import detect_episodes
from app.scoring.stats import wilson_interval


@dataclass
class EngineScoring:
    """Everything derived from one engine under one scenario."""

    outcome: EngineOutcome
    episodes: list[AlertEpisode]
    active: np.ndarray
    eligible_cycles: int
    alarm_eligible_cycles: int
    new_eligible_episodes: int
    scored_cycles: int


def score_engine(
    equipment_id: str,
    scores: np.ndarray,
    cycles: np.ndarray,
    rul: np.ndarray,
    threshold: float,
    *,
    config: ExperimentConfig = EXPERIMENT,
    valid: np.ndarray | None = None,
) -> EngineScoring:
    """Apply the alert rule to one engine and derive its outcome."""
    scores = np.asarray(scores, dtype=np.float64)
    rul = np.asarray(rul, dtype=int)
    cycles = np.asarray(cycles, dtype=int)
    valid_mask = np.isfinite(scores) if valid is None else (np.asarray(valid, bool) & np.isfinite(scores))

    active, episodes = detect_episodes(
        scores, cycles, rul, threshold, config=config, valid=valid_mask
    )

    useful = (rul >= config.min_useful_lead) & (rul <= config.horizon_cycles) & valid_mask
    late_zone = (rul >= 1) & (rul <= config.late_window_end) & valid_mask
    eligible = (rul > config.transition_band_end) & valid_mask

    detected = bool((active & useful).any())
    late = bool((not detected) and (active & late_zone).any())
    missed = not detected and not late

    lead_time: int | None = None
    if detected:
        for episode in episodes:
            # start_rul is the largest rul in the episode, end_rul the smallest.
            overlaps = episode.start_rul >= config.min_useful_lead and episode.end_rul <= config.horizon_cycles
            if overlaps:
                lead_time = int(episode.start_rul)
                break
        if lead_time is None:
            # Fall back to the first cycle inside the window that is in alarm.
            inside = np.flatnonzero(active & useful)
            lead_time = int(rul[inside[0]]) if inside.size else None

    # New episodes that opened while the engine was still far from failure.
    episode_open = np.zeros(active.shape[0], dtype=bool)
    if active.any():
        episode_open[0] = active[0]
        episode_open[1:] = active[1:] & ~active[:-1]

    return EngineScoring(
        outcome=EngineOutcome(
            equipment_id=str(equipment_id),
            detected=detected,
            late=late,
            missed=missed,
            lead_time=lead_time,
            episode_count=len(episodes),
        ),
        episodes=episodes,
        active=active,
        eligible_cycles=int(eligible.sum()),
        alarm_eligible_cycles=int((active & eligible).sum()),
        new_eligible_episodes=int((episode_open & eligible).sum()),
        scored_cycles=int(valid_mask.sum()),
    )


def aggregate(
    scorings: list[EngineScoring], *, config: ExperimentConfig = EXPERIMENT, level: float = 0.95
) -> AlertMetrics:
    """Combine per-engine scorings into the reported measures."""
    if not scorings:
        return AlertMetrics(
            engines=0,
            detected=0,
            late=0,
            missed=0,
            detection_fraction=0.0,
            detection_ci=wilson_interval(0, 0, level),
            early_alarm_burden=0.0,
            new_episodes_per_1000=0.0,
            median_lead_time=None,
            eligible_cycles=0,
            scored_cycles=0,
        )

    engines = len(scorings)
    detected = sum(1 for s in scorings if s.outcome.detected)
    late = sum(1 for s in scorings if s.outcome.late)
    missed = sum(1 for s in scorings if s.outcome.missed)

    eligible = sum(s.eligible_cycles for s in scorings)
    alarm_eligible = sum(s.alarm_eligible_cycles for s in scorings)
    new_episodes = sum(s.new_eligible_episodes for s in scorings)
    scored = sum(s.scored_cycles for s in scorings)

    leads = [s.outcome.lead_time for s in scorings if s.outcome.lead_time is not None]

    return AlertMetrics(
        engines=engines,
        detected=detected,
        late=late,
        missed=missed,
        detection_fraction=detected / engines,
        detection_ci=wilson_interval(detected, engines, level),
        early_alarm_burden=(alarm_eligible / eligible) if eligible else 0.0,
        new_episodes_per_1000=(1000.0 * new_episodes / eligible) if eligible else 0.0,
        median_lead_time=float(np.median(leads)) if leads else None,
        eligible_cycles=eligible,
        scored_cycles=scored,
    )
