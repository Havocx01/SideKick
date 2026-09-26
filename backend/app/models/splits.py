"""Engine-level partitions."""

from __future__ import annotations

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.data.dataset import Dataset
from app.schemas import SplitAssignment
from app.utils.determinism import derive_seed


def make_splits(
    dataset: Dataset,
    config: ExperimentConfig = EXPERIMENT,
    *,
    holdout_engines: int | None = None,
    n_folds: int | None = None,
) -> SplitAssignment:
    holdoutSize = config.holdout_engines if holdout_engines is None else holdout_engines
    folds = config.n_folds if n_folds is None else n_folds

    equipment = sorted(dataset.equipment_ids)
    required = holdoutSize + folds
    if len(equipment) < required:
        raise ValueError(
            f"{len(equipment)} engines cannot support a {holdoutSize}-engine holdout "
            f"plus {folds} grouped folds, which needs at least {required}"
        )

    seed = derive_seed(config.base_seed, "splits", dataset.data_hash, holdoutSize, folds)
    generator = np.random.default_rng(seed)
    shuffled = list(generator.permutation(equipment))

    holdout = sorted(str(e) for e in shuffled[:holdoutSize])
    development = sorted(str(e) for e in shuffled[holdoutSize:])

    # Deal development engines round-robin so fold sizes differ by at most one.
    foldMembers: list[list[str]] = [[] for _ in range(folds)]
    for index, equipmentId in enumerate(development):
        foldMembers[index % folds].append(equipmentId)

    assignment = SplitAssignment(
        holdout=holdout,
        development=development,
        folds=[sorted(members) for members in foldMembers],
        seed=seed,
        config_fingerprint=config.fingerprint(),
    )
    validate_splits(assignment)
    return assignment


def validate_splits(splits: SplitAssignment) -> None:
    holdout = set(splits.holdout)
    development = set(splits.development)

    overlap = holdout & development
    if overlap:
        raise ValueError(f"engines appear in both holdout and development: {sorted(overlap)}")

    seen: set[str] = set()
    for index, fold in enumerate(splits.folds):
        duplicated = seen & set(fold)
        if duplicated:
            raise ValueError(f"fold {index} repeats engines from an earlier fold: {sorted(duplicated)}")
        seen |= set(fold)

    if seen != development:
        missing = development - seen
        extra = seen - development
        raise ValueError(
            f"folds do not cover development exactly (missing {sorted(missing)}, unexpected {sorted(extra)})"
        )
    if any(not fold for fold in splits.folds):
        raise ValueError("every fold must contain at least one engine")


def fold_pairs(splits: SplitAssignment) -> list[tuple[list[str], list[str]]]:
    development = list(splits.development)
    pairs: list[tuple[list[str], list[str]]] = []
    for fold in splits.folds:
        validation = set(fold)
        train = [e for e in development if e not in validation]
        pairs.append((train, sorted(validation)))
    return pairs
