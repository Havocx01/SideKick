"""Per-engine replay series for the warning replay view."""

from __future__ import annotations

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.faults.inject import apply_fault
from app.models.design import EngineBlock, design_from_blocks
from app.models.train import TrainingResult
from app.schemas import CLEAN_SCENARIO_ID, FaultSpec, ReplayPoint, ReplaySeries
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
    fold = training.fold_for(equipment_id)
    candidate = fold.candidates[candidate_name]
    block = fold.blocks[equipment_id]
    builder = fold.builder
    return build_fitted_series(training.dataset, builder, candidate, block, equipment_id, threshold, spec=spec, config=config)


def build_fitted_series(dataset, builder, candidate, block, equipment_id, threshold, *, spec=None, config=EXPERIMENT):
    scorable = block.scorable

    if not scorable.any():
        return None

    readings = dataset.sensor_matrix(equipment_id)
    sensorClean: np.ndarray | None = None
    sensorFaulted: np.ndarray | None = None
    onsetRul: int | None = None
    affectedCycles = 0

    if spec is None:
        design = design_from_blocks({equipment_id: block}, builder.feature_names(), equipment_ids=[equipment_id])
    else:
        if spec.sensor not in builder.preprocessor.sensors:
            return None
        index = builder.preprocessor.index_of(spec.sensor)
        injected = apply_fault(
            readings[:, index], block.rul, spec, sensor_std=builder.preprocessor.std_of(spec.sensor), config=config
        )
        if not injected.applied:
            return None
        features = block.features.copy()
        builder.rebuild_sensor(features, injected.values, spec.sensor)
        faultedBlock = EngineBlock(
            equipment_id=equipment_id,
            features=features,
            labels=block.labels,
            cycles=block.cycles,
            rul=block.rul,
            rows=block.rows,
            scorable=scorable,
        )
        design = design_from_blocks({equipment_id: faultedBlock}, builder.feature_names(), equipment_ids=[equipment_id])
        sensorClean = readings[scorable, index]
        sensorFaulted = injected.values[scorable]
        affectedCycles = injected.affected_cycles
        if injected.onset_index is not None:
            onsetRul = int(block.rul[injected.onset_index])

    scores = candidate.score(design)
    scoring = score_engine(equipment_id, scores, design.cycle, design.rul, threshold, config=config)

    points = [
        ReplayPoint(
            cycle=int(design.cycle[position]),
            rul=int(design.rul[position]),
            score=float(scores[position]),
            alert=bool(scoring.active[position]),
            sensor_clean=(
                float(sensorClean[position]) if sensorClean is not None and np.isfinite(sensorClean[position]) else None
            ),
            sensor_faulted=(
                float(sensorFaulted[position])
                if sensorFaulted is not None and np.isfinite(sensorFaulted[position])
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
        fault_onset_rul=onsetRul,
        fault_affected_cycles=affectedCycles,
        points=points,
        episodes=scoring.episodes,
        outcome=scoring.outcome,
        failure_cycle=int(dataset.failure_cycles[equipment_id]),
    )


def choose_replay_engines(
    training: TrainingResult,
    candidate_name: str,
    threshold: float,
    *,
    limit: int = 6,
    config: ExperimentConfig = EXPERIMENT,
) -> list[str]:
    perEngine = training.out_of_fold[candidate_name]
    detected: list[str] = []
    late: list[str] = []
    missed: list[str] = []

    for equipmentId, engine in sorted(perEngine.items()):
        scoring = score_engine(equipmentId, engine.scores, engine.cycles, engine.rul, threshold, config=config)
        if scoring.outcome.missed:
            missed.append(equipmentId)
        elif scoring.outcome.late:
            late.append(equipmentId)
        else:
            detected.append(equipmentId)

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
