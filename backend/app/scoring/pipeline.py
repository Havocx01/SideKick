"""The end-to-end evaluation, wired together in one place.

This is the order the proposal commits to, and the order matters:

1. Split by engine, holding twenty back.
2. Fit preprocessing inside each fold, on training engines only.
3. Train every candidate, collect out-of-fold predictions.
4. Choose each candidate's alert threshold on clean out-of-fold data, then freeze it.
5. Run the fault matrix at those frozen thresholds.
6. Apply the acceptance criteria and rank, or decline to recommend.

Step 4 happens before step 5 on purpose. Choosing thresholds after seeing fault
results would tune each model to the test it is about to sit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.data.profiler import profile_dataset
from app.faults.matrix import full_scenarios, required_scenarios
from app.faults.runner import MatrixOutcome, clean_scorings, run_matrix, score_clean, to_scenario_results
from app.models.calibration import calibration_report
from app.models.candidates import candidate_grid
from app.models.thresholds import ThresholdChoice, choose_threshold
from app.models.train import TrainingResult, train_development
from app.schemas import (
    AcceptanceCriteria,
    AlertMetrics,
    CalibrationReport,
    DatasetProfile,
    FaultSpec,
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
    """Everything needed to build the evidence bundle and the three views."""

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
    training: TrainingResult,
    criteria: AcceptanceCriteria,
    *,
    config: ExperimentConfig = EXPERIMENT,
) -> dict[str, ThresholdChoice]:
    """Choose and freeze each candidate's alert threshold on clean data."""
    choices: dict[str, ThresholdChoice] = {}
    for candidate_name, per_engine in training.out_of_fold.items():
        engines = sorted(per_engine)
        pooled = np.concatenate([per_engine[e].scores for e in engines])

        def evaluate(threshold: float, engines=engines, per_engine=per_engine) -> AlertMetrics:
            scorings = [
                score_engine(
                    equipment_id,
                    per_engine[equipment_id].scores,
                    per_engine[equipment_id].cycles,
                    per_engine[equipment_id].rul,
                    threshold,
                    config=config,
                )
                for equipment_id in engines
            ]
            return aggregate(scorings, config=config)

        choice = choose_threshold(pooled, evaluate, criteria)
        if choice.note:
            logger.warning("%s: %s", candidate_name, choice.note)
        choices[candidate_name] = choice
    return choices


def evaluate(
    dataset: Dataset,
    *,
    config: ExperimentConfig = EXPERIMENT,
    criteria: AcceptanceCriteria | None = None,
    fault_sensors: list[str] | None = None,
    include_full_matrix: bool = True,
    augmentation_copies: int = 2,
) -> EvaluationResult:
    """Run the whole development evaluation on one dataset."""
    criteria = criteria or default_criteria(config)
    notes: list[str] = []

    with timed(logger, "profile"):
        profile = profile_dataset(dataset, config=config)
    if not profile.usable:
        blocking = [f.code for f in profile.findings if f.severity.value == "blocker"]
        raise ValueError(
            f"the dataset cannot be evaluated as configured: {', '.join(blocking)}"
        )

    sensors = fault_sensors if fault_sensors is not None else profile.varying_sensors
    if not sensors:
        raise ValueError("no sensor varies, so no fault test can be run")

    with timed(logger, f"training {len(candidate_grid(config))} candidates over {config.n_folds} folds"):
        training = train_development(
            dataset, config=config, augmentation_copies=augmentation_copies
        )

    with timed(logger, "threshold selection on clean out-of-fold data"):
        choices = pick_thresholds(training, criteria, config=config)
        thresholds = {name: choice.threshold for name, choice in choices.items()}
        for name, choice in choices.items():
            if not choice.within_budget:
                notes.append(f"{name}: {choice.note}")

    clean = score_clean(training, thresholds, config=config)

    required = required_scenarios(sensors, config)
    required_ids = {spec.scenario_id for spec in required}
    scenarios: list[FaultSpec] = (
        full_scenarios(sensors, config) if include_full_matrix else required
    )
    logger.info(
        "fault matrix: %d scenarios (%d required) across %d folds",
        len(scenarios),
        len(required),
        len(training.folds),
    )

    with timed(logger, "fault matrix"):
        matrix = run_matrix(training, scenarios, thresholds, config=config)

    scenario_results = to_scenario_results(
        matrix, training, thresholds, clean, required_ids=required_ids
    )

    verdicts = []
    for candidate_name, candidate in training.specs.items():
        candidate_required = [
            r
            for r in scenario_results
            if r.required
            and r.candidate == candidate.kind
            and r.config_id == candidate.config_id
        ]
        verdicts.append(
            build_verdict(
                candidate=candidate.kind,
                config_id=candidate.config_id,
                threshold=thresholds[candidate_name],
                clean=clean[candidate_name],
                required=candidate_required,
                criteria=criteria,
            )
        )

    selection = select(verdicts, criteria, partition=Partition.out_of_fold)
    selection.notes.extend(notes)

    calibration: list[CalibrationReport] = []
    for candidate_name, candidate in training.specs.items():
        scores, labels = training.pooled(candidate_name)
        if candidate.kind.value == "age_baseline":
            # Running time is not a probability, so a reliability curve over it
            # would be meaningless rather than merely unflattering.
            continue
        calibration.append(
            calibration_report(
                candidate=candidate.kind,
                config_id=candidate.config_id,
                labels=labels,
                scores=scores,
            )
        )

    return EvaluationResult(
        profile=profile,
        training=training,
        criteria=criteria,
        thresholds=thresholds,
        threshold_choices=choices,
        clean=clean,
        matrix=matrix,
        scenario_results=scenario_results,
        selection=selection,
        calibration=calibration,
        required_scenario_ids=required_ids,
        notes=notes,
    )


def clean_engine_scorings(result: EvaluationResult, candidate_name: str):
    """Per-engine clean scorings, used to build the replay view."""
    return clean_scorings(
        result.training, candidate_name, result.thresholds[candidate_name], config=result.training.config
    )
