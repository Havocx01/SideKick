"""Running the fault matrix.

The loop is ordered fold, then scenario, then candidate, because rebuilding
features from a corrupted sensor is the expensive step and it does not depend on
which model is about to read them. One rebuild therefore serves every candidate,
which turns a matrix of (scenarios x candidates) rebuilds into one of scenarios
alone. That is what keeps the full matrix inside the runtime budget.

Corruption is applied to the raw reading series and features are rebuilt from it,
never patched afterwards. A fault that changes a sensor must be allowed to change
that sensor's trailing mean and slope, because that is precisely how a real
frozen sensor misleads a model.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.faults.inject import apply_fault
from app.models.design import EngineBlock, design_from_blocks
from app.models.train import TrainingResult
from app.schemas import (
    CLEAN_SCENARIO_ID,
    AlertMetrics,
    FaultSpec,
    Partition,
    ScenarioResult,
)
from app.scoring.metrics import EngineScoring, aggregate, score_engine
from app.utils.logging_setup import get_logger, timed

logger = get_logger(__name__)


@dataclass
class MatrixOutcome:
    """Results keyed by candidate then scenario, plus what was skipped."""

    metrics: dict[tuple[str, str], AlertMetrics] = field(default_factory=dict)
    scenarios: dict[str, FaultSpec] = field(default_factory=dict)
    skipped: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    engines_scored: dict[str, int] = field(default_factory=dict)

    def for_candidate(self, candidate_name: str) -> dict[str, AlertMetrics]:
        return {
            scenario_id: metrics
            for (name, scenario_id), metrics in self.metrics.items()
            if name == candidate_name
        }


def score_clean(
    training: TrainingResult,
    thresholds: dict[str, float],
    *,
    config: ExperimentConfig = EXPERIMENT,
) -> dict[str, AlertMetrics]:
    """Clean out-of-fold measures for every candidate."""
    results: dict[str, AlertMetrics] = {}
    for candidate_name, per_engine in training.out_of_fold.items():
        threshold = thresholds[candidate_name]
        scorings = [
            score_engine(
                equipment_id,
                engine.scores,
                engine.cycles,
                engine.rul,
                threshold,
                config=config,
            )
            for equipment_id, engine in sorted(per_engine.items())
        ]
        results[candidate_name] = aggregate(scorings, config=config)
    return results


def clean_scorings(
    training: TrainingResult,
    candidate_name: str,
    threshold: float,
    *,
    config: ExperimentConfig = EXPERIMENT,
) -> list[EngineScoring]:
    per_engine = training.out_of_fold[candidate_name]
    return [
        score_engine(
            equipment_id,
            engine.scores,
            engine.cycles,
            engine.rul,
            threshold,
            config=config,
        )
        for equipment_id, engine in sorted(per_engine.items())
    ]


def run_matrix(
    training: TrainingResult,
    scenarios: list[FaultSpec],
    thresholds: dict[str, float],
    *,
    config: ExperimentConfig = EXPERIMENT,
) -> MatrixOutcome:
    """Evaluate every candidate under every scenario, out of fold.

    Each fold's models score only that fold's validation engines, so a corrupted
    engine is always unseen by the model reading it.
    """
    outcome = MatrixOutcome()
    collected: dict[tuple[str, str], list[EngineScoring]] = defaultdict(list)

    for spec in scenarios:
        outcome.scenarios[spec.scenario_id] = spec

    for fold in training.folds:
        builder = fold.builder
        preprocessor = builder.preprocessor
        feature_names = builder.feature_names()

        with timed(logger, f"fault matrix, fold {fold.fold_index + 1}: {len(scenarios)} scenarios"):
            for spec in scenarios:
                if spec.sensor not in preprocessor.sensors:
                    outcome.skipped[spec.scenario_id].append("sensor not present")
                    continue

                sensor_index = preprocessor.index_of(spec.sensor)
                sensor_std = preprocessor.std_of(spec.sensor)

                faulted: dict[str, EngineBlock] = {}
                for equipment_id in fold.validation_engines:
                    block = fold.blocks[equipment_id]
                    readings = training.dataset.sensor_matrix(equipment_id)
                    injected = apply_fault(
                        readings[:, sensor_index],
                        block.rul,
                        spec,
                        sensor_std=sensor_std,
                        config=config,
                    )
                    if not injected.applied:
                        outcome.skipped[spec.scenario_id].append(
                            f"{equipment_id}: {injected.reason}"
                        )
                        continue
                    features = block.features.copy()
                    builder.rebuild_sensor(features, injected.values, spec.sensor)
                    faulted[equipment_id] = EngineBlock(
                        equipment_id=equipment_id,
                        features=features,
                        labels=block.labels,
                        cycles=block.cycles,
                        rul=block.rul,
                        rows=block.rows,
                        scorable=block.scorable,
                    )

                if not faulted:
                    continue

                design = design_from_blocks(faulted, feature_names, equipment_ids=list(faulted))
                for candidate_name, candidate in fold.candidates.items():
                    scores = candidate.score(design)
                    for equipment_id in faulted:
                        mask = design.equipment_id == equipment_id
                        collected[(candidate_name, spec.scenario_id)].append(
                            score_engine(
                                equipment_id,
                                scores[mask],
                                design.cycle[mask],
                                design.rul[mask],
                                thresholds[candidate_name],
                                config=config,
                            )
                        )

    for key, scorings in collected.items():
        outcome.metrics[key] = aggregate(scorings, config=config)
        outcome.engines_scored[key[1]] = len(scorings)

    return outcome


def to_scenario_results(
    outcome: MatrixOutcome,
    training: TrainingResult,
    thresholds: dict[str, float],
    clean: dict[str, AlertMetrics],
    *,
    required_ids: set[str],
    partition: Partition = Partition.out_of_fold,
) -> list[ScenarioResult]:
    """Flatten the matrix into the reportable, serialisable form."""
    results: list[ScenarioResult] = []
    for candidate_name, candidate in training.specs.items():
        results.append(
            ScenarioResult(
                scenario_id=CLEAN_SCENARIO_ID,
                candidate=candidate.kind,
                config_id=candidate.config_id,
                partition=partition,
                threshold=thresholds[candidate_name],
                fault=None,
                metrics=clean[candidate_name],
                required=False,
            )
        )
        for scenario_id, metrics in sorted(outcome.for_candidate(candidate_name).items()):
            results.append(
                ScenarioResult(
                    scenario_id=scenario_id,
                    candidate=candidate.kind,
                    config_id=candidate.config_id,
                    partition=partition,
                    threshold=thresholds[candidate_name],
                    fault=outcome.scenarios.get(scenario_id),
                    metrics=metrics,
                    required=scenario_id in required_ids,
                )
            )
    return results


def estimate_runtime(
    n_scenarios: int, n_folds: int, seconds_per_scenario_fold: float
) -> float:
    """Projected wall-clock seconds for a matrix, used by the runtime spike."""
    return float(n_scenarios) * float(n_folds) * float(seconds_per_scenario_fold)


def summarise_invariance(
    outcome: MatrixOutcome, candidate_name: str, clean: AlertMetrics
) -> dict[str, float]:
    """How far a candidate moves under fault, relative to clean data."""
    per_scenario = outcome.for_candidate(candidate_name)
    if not per_scenario:
        return {}
    detections = np.array([m.detection_fraction for m in per_scenario.values()])
    return {
        "clean_detection": clean.detection_fraction,
        "mean_detection": float(detections.mean()),
        "worst_detection": float(detections.min()),
        "largest_drop": float(clean.detection_fraction - detections.min()),
        "scenarios": float(len(detections)),
    }
