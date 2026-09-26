"""Cross-validated training and out-of-fold prediction."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.faults.inject import apply_fault
from app.features.build import FeatureBuilder, Preprocessor
from app.models.base import Candidate, DesignMatrix
from app.models.candidates import candidate_grid
from app.models.design import EngineBlock, assert_engine_disjoint, design_from_blocks, engine_blocks
from app.models.splits import fold_pairs, make_splits
from app.schemas import FaultDuration, FaultKind, FaultSpec, SplitAssignment
from app.utils.determinism import derive_seed
from app.utils.logging_setup import get_logger, timed

logger = get_logger(__name__)

AUGMENTATION_COPIES_PER_ENGINE = 2


@dataclass
class EngineScores:
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
    dataset: Dataset
    splits: SplitAssignment
    folds: list[FoldFit]
    out_of_fold: dict[str, dict[str, EngineScores]]
    specs: dict[str, Candidate]
    config: ExperimentConfig

    def pooled(self, candidate_name: str) -> tuple[np.ndarray, np.ndarray]:
        perEngine = self.out_of_fold[candidate_name]
        scores = np.concatenate([perEngine[e].scores for e in sorted(perEngine)])
        labels = np.concatenate([perEngine[e].labels for e in sorted(perEngine)])
        return scores, labels

    def fold_for(self, equipment_id: str) -> FoldFit:
        for fold in self.folds:
            if equipment_id in fold.validation_engines:
                return fold
        raise KeyError(f"{equipment_id} is not a validation engine in any fold")


def sample_augmentation_faults(sensors: list[str], seed: int, copies: int, config: ExperimentConfig) -> list[FaultSpec]:
    """Training faults are sampled independently of the fixed evaluation grid."""
    generator = np.random.default_rng(seed)
    kinds = [FaultKind.dropout, FaultKind.stuck, FaultKind.drift]
    specs: list[FaultSpec] = []
    for copyIndex in range(copies):
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
                seed=derive_seed(seed, "augment", copyIndex),
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
    eligible = [s for s in builder.sensors if builder.preprocessor.std_of(s) > 0]
    if not eligible:
        return None

    parts: list[EngineBlock] = []
    for equipmentId in train_engines:
        block = blocks[equipmentId]
        readings = dataset.sensor_matrix(equipmentId)
        engineSeed = derive_seed(seed, "augment_engine", equipmentId)
        for copyIndex, spec in enumerate(sample_augmentation_faults(eligible, engineSeed, copies, config)):
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
                    equipment_id=f"{equipmentId}~aug{copyIndex}",
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
    progress=None,
) -> TrainingResult:
    config.validate()
    splits = splits or make_splits(dataset, config)
    grid = candidates if candidates is not None else candidate_grid(config)
    specs = {candidate.name: candidate for candidate in grid}

    development = dataset.subset(splits.development)
    outOfFold: dict[str, dict[str, EngineScores]] = {name: {} for name in specs}
    folds: list[FoldFit] = []

    for foldIndex, (trainEngines, validationEngines) in enumerate(fold_pairs(splits)):
        with timed(logger, f"fold {foldIndex + 1}/{len(splits.folds)}"):
            trainRows = development.frame["equipment_id"].isin(trainEngines).to_numpy()
            trainRows &= development.scorable_mask()
            preprocessor = Preprocessor.fit(development, trainRows)
            builder = FeatureBuilder(preprocessor, config)

            blocks = engine_blocks(development, builder)
            trainDesign = design_from_blocks(blocks, builder.feature_names(), equipment_ids=trainEngines)
            validationDesign = design_from_blocks(blocks, builder.feature_names(), equipment_ids=validationEngines)
            assert_engine_disjoint(trainDesign, validationDesign)
            trainDesign.assert_finite()
            validationDesign.assert_finite()

            augmented: DesignMatrix | None = None
            if any(c.requires_augmentation for c in grid):
                augmented = build_augmented_design(
                    development,
                    builder,
                    blocks,
                    trainEngines,
                    seed=derive_seed(config.base_seed, "augmentation", foldIndex),
                    config=config,
                    copies=augmentation_copies,
                )
                if augmented is None:
                    logger.warning("fold %d produced no augmented rows", foldIndex)

            fitted: dict[str, Candidate] = {}
            for template in grid:
                candidate = type(template)(template.config_id, dict(template.params))
                candidate.fit(trainDesign, augmented=augmented)
                fitted[candidate.name] = candidate

                scores = candidate.score(validationDesign)
                for equipmentId in validationEngines:
                    mask = validationDesign.equipment_id == equipmentId
                    outOfFold[candidate.name][equipmentId] = EngineScores(
                        equipment_id=equipmentId,
                        cycles=validationDesign.cycle[mask],
                        rul=validationDesign.rul[mask],
                        scores=scores[mask],
                        labels=validationDesign.y[mask],
                    )

            folds.append(
                FoldFit(
                    fold_index=foldIndex,
                    train_engines=list(trainEngines),
                    validation_engines=list(validationEngines),
                    preprocessor=preprocessor,
                    builder=builder,
                    candidates=fitted,
                    blocks=blocks,
                )
            )
            if progress:
                progress("training", foldIndex + 1, len(splits.folds), "folds completed")

    covered = {e for scores in outOfFold.values() for e in scores}
    if covered != set(splits.development):
        missing = set(splits.development) - covered
        raise AssertionError(f"engines have no out-of-fold prediction: {sorted(missing)}")

    return TrainingResult(
        dataset=development, splits=splits, folds=folds, out_of_fold=outOfFold, specs=specs, config=config
    )


def fit_final(
    dataset: Dataset,
    splits: SplitAssignment,
    candidate: Candidate,
    *,
    config: ExperimentConfig = EXPERIMENT,
    augmentation_copies: int = AUGMENTATION_COPIES_PER_ENGINE,
) -> tuple[Candidate, FeatureBuilder, Preprocessor]:
    """Refit on development equipment only; the reserved equipment must remain unseen."""
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
