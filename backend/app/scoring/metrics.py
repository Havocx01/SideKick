"""Operational measures."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import AlertEpisode, AlertMetrics, EngineOutcome
from app.scoring.episodes import detect_episodes
from app.scoring.stats import wilson_interval


@dataclass
class EngineScoring:
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
    scores = np.asarray(scores, dtype=np.float64)
    rul = np.asarray(rul, dtype=int)
    cycles = np.asarray(cycles, dtype=int)
    validMask = np.isfinite(scores) if valid is None else (np.asarray(valid, bool) & np.isfinite(scores))

    active, episodes = detect_episodes(scores, cycles, rul, threshold, config=config, valid=validMask)

    useful = (rul >= config.min_useful_lead) & (rul <= config.horizon_cycles) & validMask
    lateZone = (rul >= 1) & (rul <= config.late_window_end) & validMask
    eligible = (rul > config.transition_band_end) & validMask

    detected = bool((active & useful).any())
    late = bool((not detected) and (active & lateZone).any())
    missed = not detected and not late

    leadTime: int | None = None
    if detected:
        for episode in episodes:
            # start_rul is the largest rul in the episode, end_rul the smallest.
            overlaps = episode.start_rul >= config.min_useful_lead and episode.end_rul <= config.horizon_cycles
            if overlaps:
                leadTime = int(episode.start_rul)
                break
        if leadTime is None:
            inside = np.flatnonzero(active & useful)
            leadTime = int(rul[inside[0]]) if inside.size else None

    episodeOpen = np.zeros(active.shape[0], dtype=bool)
    if active.any():
        episodeOpen[0] = active[0]
        episodeOpen[1:] = active[1:] & ~active[:-1]

    return EngineScoring(
        outcome=EngineOutcome(
            equipment_id=str(equipment_id),
            detected=detected,
            late=late,
            missed=missed,
            lead_time=leadTime,
            episode_count=len(episodes),
        ),
        episodes=episodes,
        active=active,
        eligible_cycles=int(eligible.sum()),
        alarm_eligible_cycles=int((active & eligible).sum()),
        new_eligible_episodes=int((episodeOpen & eligible).sum()),
        scored_cycles=int(validMask.sum()),
    )


def aggregate(
    scorings: list[EngineScoring], *, config: ExperimentConfig = EXPERIMENT, level: float = 0.95
) -> AlertMetrics:
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
    alarmEligible = sum(s.alarm_eligible_cycles for s in scorings)
    newEpisodes = sum(s.new_eligible_episodes for s in scorings)
    scored = sum(s.scored_cycles for s in scorings)

    leads = [s.outcome.lead_time for s in scorings if s.outcome.lead_time is not None]

    return AlertMetrics(
        engines=engines,
        detected=detected,
        late=late,
        missed=missed,
        detection_fraction=detected / engines,
        detection_ci=wilson_interval(detected, engines, level),
        early_alarm_burden=(alarmEligible / eligible) if eligible else 0.0,
        new_episodes_per_1000=(1000.0 * newEpisodes / eligible) if eligible else 0.0,
        median_lead_time=float(np.median(leads)) if leads else None,
        eligible_cycles=eligible,
        scored_cycles=scored,
    )
