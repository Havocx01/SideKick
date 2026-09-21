"""Per-engine replay series for the warning replay view.

The view exists to answer one question concretely: what did the model see, and
when did it warn? So each series carries the score at every cycle, the alert
episodes derived from it, and both the original and the altered reading for the
sensor under test, on the same time axis.
"""

from __future__ import annotations

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.faults.inject import apply_fault
from app.models.design import EngineBlock, design_from_blocks
from app.models.train import TrainingResult
from app.schemas import (
    CLEAN_SCENARIO_ID,
    FaultSpec,
    ReplayPoint,
    ReplaySeries,
)
from app.scoring.metrics import score_engine


def build_series(
    training: TrainingResult,
    candidate_name: str,
    equipment_id: str,
    threshold: float,
    *,
    spec: FaultSpec | None = None,
    config: ExperimentConfig = EXPERIMENT,
) -> ReplaySeries | None:
    """Build one engine's replay series, clean or under one fault."""
    fold = training.fold_for(equipment_id)
    candidate = fold.candidates[candidate_name]
    block = fold.blocks[equipment_id]
    builder = fold.builder
    scorable = block.scorable

    if not scorable.any():
        return None

    readings = training.dataset.sensor_matrix(equipment_id)
    sensor_clean: np.ndarray | None = None
    sensor_faulted: np.ndarray | None = None
    onset_rul: int | None = None
    affected_cycles = 0

    if spec is None:
        design = design_from_blocks(
            {equipment_id: block}, builder.feature_names(), equipment_ids=[equipment_id]
        )
    else:
        if spec.sensor not in builder.preprocessor.sensors:
            return None
        index = builder.preprocessor.index_of(spec.sensor)
        injected = apply_fault(
            readings[:, index],
            block.rul,
            spec,
            sensor_std=builder.preprocessor.std_of(spec.sensor),
            config=config,
        )
        if not injected.applied:
            return None
        features = block.features.copy()
        builder.rebuild_sensor(features, injected.values, spec.sensor)
        faulted_block = EngineBlock(
            equipment_id=equipment_id,
            features=features,
            labels=block.labels,
            cycles=block.cycles,
            rul=block.rul,
            rows=block.rows,
            scorable=scorable,
        )
        design = design_from_blocks(
            {equipment_id: faulted_block}, builder.feature_names(), equipment_ids=[equipment_id]
        )
        sensor_clean = readings[scorable, index]
        sensor_faulted = injected.values[scorable]
        affected_cycles = injected.affected_cycles
        if injected.onset_index is not None:
            onset_rul = int(block.rul[injected.onset_index])

    scores = candidate.score(design)
    scoring = score_engine(
        equipment_id, scores, design.cycle, design.rul, threshold, config=config
    )

    points = [
        ReplayPoint(
            cycle=int(design.cycle[position]),
            rul=int(design.rul[position]),
            score=float(scores[position]),
            alert=bool(scoring.active[position]),
            sensor_clean=(
                float(sensor_clean[position])
                if sensor_clean is not None and np.isfinite(sensor_clean[position])
                else None
            ),
            sensor_faulted=(
                float(sensor_faulted[position])
                if sensor_faulted is not None and np.isfinite(sensor_faulted[position])
                else None
            ),
        )
        for position in range(len(design))
    ]

    return ReplaySeries(
        equipment_id=equipment_id,
        candidate=candidate.kind,
        config_id=candidate.config_id,
        scenario_id=spec.scenario_id if spec else CLEAN_SCENARIO_ID,
        threshold=threshold,
        fault=spec,
        fault_onset_rul=onset_rul,
        fault_affected_cycles=affected_cycles,
        points=points,
        episodes=scoring.episodes,
        outcome=scoring.outcome,
        failure_cycle=int(training.dataset.failure_cycles[equipment_id]),
    )


def choose_replay_engines(
    training: TrainingResult,
    candidate_name: str,
    threshold: float,
    *,
    limit: int = 6,
    config: ExperimentConfig = EXPERIMENT,
) -> list[str]:
    """Pick engines worth showing: a mix of detections, late warnings and misses.

    A demo that only shows successes is not evidence. Including the failures the
    evaluation actually found is the point of the view.
    """
    per_engine = training.out_of_fold[candidate_name]
    detected: list[str] = []
    late: list[str] = []
    missed: list[str] = []

    for equipment_id, engine in sorted(per_engine.items()):
        scoring = score_engine(
            equipment_id, engine.scores, engine.cycles, engine.rul, threshold, config=config
        )
        if scoring.outcome.missed:
            missed.append(equipment_id)
        elif scoring.outcome.late:
            late.append(equipment_id)
        else:
            detected.append(equipment_id)

    chosen: list[str] = []
    # Round-robin across the three outcomes so the selection is not all successes.
    for group in _interleave(missed, late, detected):
        if group not in chosen:
            chosen.append(group)
        if len(chosen) >= limit:
            break
    return chosen


def _interleave(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for position in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if position < len(group):
                result.append(group[position])
    return result
