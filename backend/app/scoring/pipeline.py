"""The end-to-end evaluation, wired together in one place."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.data.profiler import profile_dataset
from app.faults.matrix import full_scenarios, required_scenarios
from app.faults.runner import MatrixOutcome, run_matrix, score_clean, to_scenario_results
from app.models.calibration import calibration_report
from app.models.candidates import candidate_grid
from app.models.thresholds import ThresholdChoice, choose_threshold
from app.models.train import TrainingResult, train_development
from app.schemas import (
    AcceptanceCriteria,
    AlertMetrics,
    CalibrationReport,
    DatasetProfile,
    FaultScenario,
    Partition,
    ScenarioResult,
    SelectionResult,
)
from app.scoring.metrics import aggregate, score_engine
from app.scoring.selection import build_verdict, default_criteria, select
from app.utils.logging_setup import get_logger, timed

logger = get_logger(__name__)


@dataclass
class EvaluationResult:
    profile: DatasetProfile
    training: TrainingResult
    criteria: AcceptanceCriteria
    thresholds: dict[str, float]
    threshold_choices: dict[str, ThresholdChoice]
    clean: dict[str, AlertMetrics]
    matrix: MatrixOutcome
    scenario_results: list[ScenarioResult]
    selection: SelectionResult
    calibration: list[CalibrationReport] = field(default_factory=list)
    required_scenario_ids: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)


def pick_thresholds(
    training: TrainingResult, criteria: AcceptanceCriteria, *, config: ExperimentConfig = EXPERIMENT
) -> dict[str, ThresholdChoice]:
    choices: dict[str, ThresholdChoice] = {}
    for candidateName, perEngine in training.out_of_fold.items():
        engines = sorted(perEngine)
        pooled = np.concatenate([perEngine[e].scores for e in engines])

        def evaluate(threshold: float, engines=engines, per_engine=perEngine) -> AlertMetrics:
            scorings = [
                score_engine(
                    equipmentId,
                    per_engine[equipmentId].scores,
                    per_engine[equipmentId].cycles,
                    per_engine[equipmentId].rul,
                    threshold,
                    config=config,
                )
                for equipmentId in engines
            ]
            return aggregate(scorings, config=config)

        choice = choose_threshold(pooled, evaluate, criteria)
        if choice.note:
            logger.warning("%s: %s", candidateName, choice.note)
        choices[candidateName] = choice
    return choices


def evaluate(
    dataset: Dataset,
    *,
    config: ExperimentConfig = EXPERIMENT,
    criteria: AcceptanceCriteria | None = None,
    fault_sensors: list[str] | None = None,
    include_full_matrix: bool = True,
    augmentation_copies: int = 2,
    progress=None,
) -> EvaluationResult:
    criteria = criteria or default_criteria(config)
    if criteria.min_useful_lead != config.min_useful_lead or criteria.horizon_cycles != config.horizon_cycles:
        raise ValueError("Criteria warning windows must match the experiment configuration")
    config = replace(
        config,
        min_detection_fraction=criteria.min_detection_fraction,
        max_early_alarm_burden=criteria.max_early_alarm_burden,
    )
    config.validate()
    dataset = replace(dataset, config=config)
    notes: list[str] = []

    with timed(logger, "profile"):
        profile = profile_dataset(dataset, config=config)
    if not profile.usable:
        blocking = [f.code for f in profile.findings if f.severity.value == "blocker"]
        raise ValueError(f"the dataset cannot be evaluated as configured: {', '.join(blocking)}")

    sensors = fault_sensors if fault_sensors is not None else profile.varying_sensors
    if not sensors:
        raise ValueError("no sensor varies, so no fault test can be run")

    if progress:
        progress("training", 0, config.n_folds, "folds completed")
    with timed(logger, f"training {len(candidate_grid(config))} candidates over {config.n_folds} folds"):
        training = train_development(dataset, config=config, augmentation_copies=augmentation_copies, progress=progress)

    if progress:
        progress("selecting thresholds", 0, None, "using clean out-of-fold predictions")
    with timed(logger, "threshold selection on clean out-of-fold data"):
        choices = pick_thresholds(training, criteria, config=config)
        thresholds = {name: choice.threshold for name, choice in choices.items()}
        for name, choice in choices.items():
            if not choice.within_budget:
                notes.append(f"{name}: {choice.note}")

    clean = score_clean(training, thresholds, config=config)

    if config.fault_scenarios is not None:
        entries = [FaultScenario.model_validate(s) for s in config.fault_scenarios]
        required = [s.fault for s in entries if s.required]
        scenarios = [s.fault for s in entries]
    else:
        required = required_scenarios(sensors, config)
        scenarios = full_scenarios(sensors, config) if include_full_matrix else required
    requiredIds = {spec.scenario_id for spec in required}
    logger.info(
        "fault matrix: %d scenarios (%d required) across %d folds", len(scenarios), len(required), len(training.folds)
    )

    with timed(logger, "fault matrix"):
        matrix = run_matrix(training, scenarios, thresholds, config=config, progress=progress)

    scenarioResults = to_scenario_results(matrix, training, thresholds, clean, required_ids=requiredIds)

    verdicts = []
    for candidateName, candidate in training.specs.items():
        candidateRequired = [
            r
            for r in scenarioResults
            if r.required and r.candidate == candidate.kind and r.config_id == candidate.config_id
        ]
        verdicts.append(
            build_verdict(
                candidate=candidate.kind,
                config_id=candidate.config_id,
                threshold=thresholds[candidateName],
                clean=clean[candidateName],
                required=candidateRequired,
                criteria=criteria,
            )
        )
        verdict = verdicts[-1]
        incomplete = len(candidateRequired) != len(requiredIds) or any(
            row.metrics.engines != len(training.splits.development) for row in candidateRequired
        )
        if incomplete:
            verdict.qualifies = False
            verdict.passes_all_required = False
            verdict.coverage_complete = False
            verdict.notes.append(
                "Required fault coverage is incomplete. Every required case must score all development engines."
            )

    selection = select(verdicts, criteria, partition=Partition.out_of_fold)
    selection.notes.extend(notes)

    calibration: list[CalibrationReport] = []
    for candidateName, candidate in training.specs.items():
        scores, labels = training.pooled(candidateName)
        if candidate.kind.value == "age_baseline":
            # Running time is not a probability and cannot use a reliability curve.
            continue
        calibration.append(
            calibration_report(candidate=candidate.kind, config_id=candidate.config_id, labels=labels, scores=scores)
        )

    return EvaluationResult(
        profile=profile,
        training=training,
        criteria=criteria,
        thresholds=thresholds,
        threshold_choices=choices,
        clean=clean,
        matrix=matrix,
        scenario_results=scenarioResults,
        selection=selection,
        calibration=calibration,
        required_scenario_ids=requiredIds,
        notes=notes,
    )
