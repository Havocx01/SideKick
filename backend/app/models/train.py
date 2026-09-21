"""Cross-validated training and out-of-fold prediction.

Preprocessing is fitted inside each fold, on that fold's training engines only.
Imputation medians and the standard deviations that scale drift severity therefore
never see a validation engine, which is what lets an out-of-fold score stand in
for performance on an unseen machine.

Fault augmentation is also per fold, with its own derived seed, so the corrupted
copies mixed into one fold's training set are independent of another's.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.faults.inject import apply_fault
from app.features.build import FeatureBuilder, Preprocessor
from app.models.base import Candidate, DesignMatrix
from app.models.candidates import candidate_grid
from app.models.design import (
    EngineBlock,
    assert_engine_disjoint,
    design_from_blocks,
    engine_blocks,
)
from app.models.splits import fold_pairs, make_splits
from app.schemas import FaultDuration, FaultKind, FaultSpec, SplitAssignment
from app.utils.determinism import derive_seed, rng
from app.utils.logging_setup import get_logger, timed

logger = get_logger(__name__)

#: Corrupted copies added per training engine in the augmented variant.
AUGMENTATION_COPIES_PER_ENGINE = 2


@dataclass
class EngineScores:
    """One candidate's scores for one engine's scorable cycles."""

    equipment_id: str
    cycles: np.ndarray
    rul: np.ndarray
    scores: np.ndarray
    labels: np.ndarray


@dataclass
class FoldFit:
    fold_index: int
    train_engines: list[str]
    validation_engines: list[str]
    preprocessor: Preprocessor
    builder: FeatureBuilder
    candidates: dict[str, Candidate]
    blocks: dict[str, EngineBlock] = field(default_factory=dict)


@dataclass
class TrainingResult:
    """Everything produced by development training."""

    dataset: Dataset
    splits: SplitAssignment
    folds: list[FoldFit]
    out_of_fold: dict[str, dict[str, EngineScores]]
    specs: dict[str, Candidate]
    config: ExperimentConfig

    def candidate_names(self) -> list[str]:
        return list(self.specs)

    def pooled(self, candidate_name: str) -> tuple[np.ndarray, np.ndarray]:
        """Concatenated out-of-fold scores and labels for one candidate."""
        per_engine = self.out_of_fold[candidate_name]
        scores = np.concatenate([per_engine[e].scores for e in sorted(per_engine)])
        labels = np.concatenate([per_engine[e].labels for e in sorted(per_engine)])
        return scores, labels

    def fold_for(self, equipment_id: str) -> FoldFit:
        for fold in self.folds:
            if equipment_id in fold.validation_engines:
                return fold
        raise KeyError(f"{equipment_id} is not a validation engine in any fold")


def sample_augmentation_faults(
    sensors: list[str], seed: int, copies: int, config: ExperimentConfig
) -> list[FaultSpec]:
    """Draw fault specifications for training-time augmentation.

    Positions, kinds and severities are sampled rather than fixed, so the
    augmented model sees variety instead of memorising the exact cases it will
    later be tested on. Onsets are drawn from a wider range than the test onsets
    for the same reason.
    """
    generator = np.random.default_rng(seed)
    kinds = [FaultKind.dropout, FaultKind.stuck, FaultKind.drift]
    specs: list[FaultSpec] = []
    for copy_index in range(copies):
        sensor = str(generator.choice(sensors))
        kind = kinds[int(generator.integers(0, len(kinds)))]
        onset = int(generator.integers(config.min_useful_lead + 5, 120))
        specs.append(
            FaultSpec(
                kind=kind,
                duration=FaultDuration.persistent,
                sensor=sensor,
                onset_before_failure=onset,
                severity_sd=float(generator.uniform(0.5, 2.5)) if kind == FaultKind.drift else None,
                sign=int(generator.choice([-1, 1])) if kind == FaultKind.drift else None,
                ramp_cycles=config.drift_ramp_cycles if kind == FaultKind.drift else None,
                seed=derive_seed(seed, "augment", copy_index),
            )
        )
    return specs


def build_augmented_design(
    dataset: Dataset,
    builder: FeatureBuilder,
    blocks: dict[str, EngineBlock],
    train_engines: list[str],
    *,
    seed: int,
    config: ExperimentConfig,
    copies: int = AUGMENTATION_COPIES_PER_ENGINE,
) -> DesignMatrix | None:
    """Corrupted copies of the training engines, with labels unchanged."""
    eligible = [s for s in builder.sensors if builder.preprocessor.std_of(s) > 0]
    if not eligible:
        return None

    parts: list[EngineBlock] = []
    for engine_index, equipment_id in enumerate(train_engines):
        block = blocks[equipment_id]
        readings = dataset.sensor_matrix(equipment_id)
        engine_seed = derive_seed(seed, "augment_engine", equipment_id)
        for spec in sample_augmentation_faults(eligible, engine_seed, copies, config):
            result = apply_fault(
                readings[:, builder.preprocessor.index_of(spec.sensor)],
                block.rul,
                spec,
                sensor_std=builder.preprocessor.std_of(spec.sensor),
                config=config,
            )
            if not result.applied:
                continue
            features = block.features.copy()
            builder.rebuild_sensor(features, result.values, spec.sensor)
            parts.append(
                EngineBlock(
                    equipment_id=f"{equipment_id}~aug{engine_index}",
                    features=features,
                    labels=block.labels,
                    cycles=block.cycles,
                    rul=block.rul,
                    rows=block.rows,
                    scorable=block.scorable,
                )
            )

    if not parts:
        return None
    keyed = {block.equipment_id: block for block in parts}
    return design_from_blocks(keyed, builder.feature_names(), equipment_ids=list(keyed))


def train_development(
    dataset: Dataset,
    *,
    config: ExperimentConfig = EXPERIMENT,
    candidates: list[Candidate] | None = None,
    splits: SplitAssignment | None = None,
    augmentation_copies: int = AUGMENTATION_COPIES_PER_ENGINE,
) -> TrainingResult:
    """Run grouped cross-validation and collect out-of-fold scores."""
    config.validate()
    splits = splits or make_splits(dataset, config)
    grid = candidates if candidates is not None else candidate_grid(config)
    specs = {candidate.name: candidate for candidate in grid}

    development = dataset.subset(splits.development)
    out_of_fold: dict[str, dict[str, EngineScores]] = {name: {} for name in specs}
    folds: list[FoldFit] = []

    for fold_index, (train_engines, validation_engines) in enumerate(fold_pairs(splits)):
        with timed(logger, f"fold {fold_index + 1}/{len(splits.folds)}"):
            train_rows = development.frame["equipment_id"].isin(train_engines).to_numpy()
            train_rows &= development.scorable_mask()
            preprocessor = Preprocessor.fit(development, train_rows)
            builder = FeatureBuilder(preprocessor, config)

            blocks = engine_blocks(development, builder)
            train_design = design_from_blocks(
                blocks, builder.feature_names(), equipment_ids=train_engines
            )
            validation_design = design_from_blocks(
                blocks, builder.feature_names(), equipment_ids=validation_engines
            )
            assert_engine_disjoint(train_design, validation_design)
            train_design.assert_finite()
            validation_design.assert_finite()

            augmented: DesignMatrix | None = None
            if any(c.requires_augmentation for c in grid):
                augmented = build_augmented_design(
                    development,
                    builder,
                    blocks,
                    train_engines,
                    seed=derive_seed(config.base_seed, "augmentation", fold_index),
                    config=config,
                    copies=augmentation_copies,
                )
                if augmented is None:
                    logger.warning("fold %d produced no augmented rows", fold_index)

            fitted: dict[str, Candidate] = {}
            for template in grid:
                candidate = type(template)(template.config_id, dict(template.params))
                candidate.fit(train_design, augmented=augmented)
                fitted[candidate.name] = candidate

                scores = candidate.score(validation_design)
                for equipment_id in validation_engines:
                    mask = validation_design.equipment_id == equipment_id
                    out_of_fold[candidate.name][equipment_id] = EngineScores(
                        equipment_id=equipment_id,
                        cycles=validation_design.cycle[mask],
                        rul=validation_design.rul[mask],
                        scores=scores[mask],
                        labels=validation_design.y[mask],
                    )

            folds.append(
                FoldFit(
                    fold_index=fold_index,
                    train_engines=list(train_engines),
                    validation_engines=list(validation_engines),
                    preprocessor=preprocessor,
                    builder=builder,
                    candidates=fitted,
                    blocks=blocks,
                )
            )

    covered = {e for scores in out_of_fold.values() for e in scores}
    if covered != set(splits.development):
        missing = set(splits.development) - covered
        raise AssertionError(f"engines have no out-of-fold prediction: {sorted(missing)}")

    return TrainingResult(
        dataset=development,
        splits=splits,
        folds=folds,
        out_of_fold=out_of_fold,
        specs=specs,
        config=config,
    )


def fit_final(
    dataset: Dataset,
    splits: SplitAssignment,
    candidate: Candidate,
    *,
    config: ExperimentConfig = EXPERIMENT,
    augmentation_copies: int = AUGMENTATION_COPIES_PER_ENGINE,
) -> tuple[Candidate, FeatureBuilder, Preprocessor]:
    """Refit one candidate on every development engine, for the final evaluation.

    Called once, after the configuration is frozen. The holdout engines are not
    touched here; they are only ever scored.
    """
    development = dataset.subset(splits.development)
    rows = development.scorable_mask()
    preprocessor = Preprocessor.fit(development, rows)
    builder = FeatureBuilder(preprocessor, config)
    blocks = engine_blocks(development, builder)
    design = design_from_blocks(blocks, builder.feature_names())
    design.assert_finite()

    augmented = None
    if candidate.requires_augmentation:
        augmented = build_augmented_design(
            development,
            builder,
            blocks,
            list(splits.development),
            seed=derive_seed(config.base_seed, "augmentation", "final"),
            config=config,
            copies=augmentation_copies,
        )

    refit = type(candidate)(candidate.config_id, dict(candidate.params))
    refit.fit(design, augmented=augmented)
    return refit, builder, preprocessor
