"""Running the fault matrix."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.config import EXPERIMENT, ExperimentConfig
from app.faults.inject import apply_fault
from app.models.design import EngineBlock, design_from_blocks
from app.models.train import TrainingResult
from app.schemas import CLEAN_SCENARIO_ID, AlertMetrics, FaultSpec, Partition, ScenarioResult
from app.scoring.metrics import EngineScoring, aggregate, compact_scoring, score_engine
from app.utils.logging_setup import get_logger, timed

logger = get_logger(__name__)


@dataclass
class MatrixOutcome:
    metrics: dict[tuple[str, str], AlertMetrics] = field(default_factory=dict)
    scenarios: dict[str, FaultSpec] = field(default_factory=dict)
    skipped: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    engines_scored: dict[str, int] = field(default_factory=dict)
    equipment_metrics: dict[tuple[str, str], list[EngineScoring]] = field(default_factory=dict)

    def for_candidate(self, candidate_name: str) -> dict[str, AlertMetrics]:
        return {scenarioId: metrics for (name, scenarioId), metrics in self.metrics.items() if name == candidate_name}


def score_clean(
    training: TrainingResult, thresholds: dict[str, float], *, config: ExperimentConfig = EXPERIMENT
) -> dict[str, AlertMetrics]:
    results: dict[str, AlertMetrics] = {}
    for candidateName, perEngine in training.out_of_fold.items():
        threshold = thresholds[candidateName]
        scorings = [
            score_engine(equipmentId, engine.scores, engine.cycles, engine.rul, threshold, config=config)
            for equipmentId, engine in sorted(perEngine.items())
        ]
        results[candidateName] = aggregate(scorings, config=config)
    return results


def run_matrix(
    training: TrainingResult,
    scenarios: list[FaultSpec],
    thresholds: dict[str, float],
    *,
    config: ExperimentConfig = EXPERIMENT,
    progress=None,
) -> MatrixOutcome:
    outcome = MatrixOutcome()
    collected: dict[tuple[str, str], list[EngineScoring]] = defaultdict(list)

    for spec in scenarios:
        outcome.scenarios[spec.scenario_id] = spec

    for fold in training.folds:
        builder = fold.builder
        preprocessor = builder.preprocessor
        featureNames = builder.feature_names()

        with timed(logger, f"fault matrix, fold {fold.fold_index + 1}: {len(scenarios)} scenarios"):
            for specIndex, spec in enumerate(scenarios):
                if progress:
                    progress(
                        "testing faults",
                        fold.fold_index * len(scenarios) + specIndex,
                        len(training.folds) * len(scenarios),
                        "scenario-fold tests completed",
                    )
                if spec.sensor not in preprocessor.sensors:
                    outcome.skipped[spec.scenario_id].append("sensor not present")
                    continue

                sensorIndex = preprocessor.index_of(spec.sensor)
                sensorStd = preprocessor.std_of(spec.sensor)

                faulted: dict[str, EngineBlock] = {}
                for equipmentId in fold.validation_engines:
                    block = fold.blocks[equipmentId]
                    readings = training.dataset.sensor_matrix(equipmentId)
                    injected = apply_fault(
                        readings[:, sensorIndex], block.rul, spec, sensor_std=sensorStd, config=config
                    )
                    if not injected.applied:
                        outcome.skipped[spec.scenario_id].append(f"{equipmentId}: {injected.reason}")
                        continue
                    features = block.features.copy()
                    builder.rebuild_sensor(features, injected.values, spec.sensor)
                    faulted[equipmentId] = EngineBlock(
                        equipment_id=equipmentId,
                        features=features,
                        labels=block.labels,
                        cycles=block.cycles,
                        rul=block.rul,
                        rows=block.rows,
                        scorable=block.scorable,
                    )

                if not faulted:
                    continue

                design = design_from_blocks(faulted, featureNames, equipment_ids=list(faulted))
                for candidateName, candidate in fold.candidates.items():
                    scores = candidate.score(design)
                    for equipmentId in faulted:
                        mask = design.equipment_id == equipmentId
                        collected[(candidateName, spec.scenario_id)].append(
                            compact_scoring(score_engine(
                                equipmentId,
                                scores[mask],
                                design.cycle[mask],
                                design.rul[mask],
                                thresholds[candidateName],
                                config=config,
                            ))
                        )

    if progress:
        count = len(training.folds) * len(scenarios)
        progress("testing faults", count, count, "scenario-fold tests completed")
    for key, scorings in collected.items():
        outcome.metrics[key] = aggregate(scorings, config=config)
        outcome.engines_scored[key[1]] = len(scorings)
        outcome.equipment_metrics[key] = scorings

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
    results: list[ScenarioResult] = []
    for candidateName, candidate in training.specs.items():
        results.append(
            ScenarioResult(
                scenario_id=CLEAN_SCENARIO_ID,
                candidate=candidate.kind,
                config_id=candidate.config_id,
                partition=partition,
                threshold=thresholds[candidateName],
                fault=None,
                metrics=clean[candidateName],
                required=False,
            )
        )
        candidateMetrics = outcome.for_candidate(candidateName)
        for scenarioId in sorted(outcome.scenarios):
            metrics = candidateMetrics.get(scenarioId) or aggregate([])
            results.append(
                ScenarioResult(
                    scenario_id=scenarioId,
                    candidate=candidate.kind,
                    config_id=candidate.config_id,
                    partition=partition,
                    threshold=thresholds[candidateName],
                    fault=outcome.scenarios.get(scenarioId),
                    metrics=metrics,
                    required=scenarioId in required_ids,
                    expected_engines=len(training.splits.development),
                    coverage_complete=metrics.engines == len(training.splits.development),
                    coverage_notes=outcome.skipped.get(scenarioId, [])[:20],
                )
            )
    return results
