"""Engine-level partitions.

Splitting by engine rather than by row is the single most important guard against
leakage here: consecutive cycles from one engine are near-duplicates, so a random
row split would let the model see a machine's own future and report a score that
cannot be reproduced on a new machine.

Twenty engines are reserved for one frozen final evaluation. The remaining
engines are divided into grouped folds, and every fold's out-of-fold predictions
come from a model that never saw that engine.
"""

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
    """Assign engines to the holdout and to grouped development folds."""
    holdout_size = config.holdout_engines if holdout_engines is None else holdout_engines
    folds = config.n_folds if n_folds is None else n_folds

    equipment = sorted(dataset.equipment_ids)
    required = holdout_size + folds
    if len(equipment) < required:
        raise ValueError(
            f"{len(equipment)} engines cannot support a {holdout_size}-engine holdout "
            f"plus {folds} grouped folds, which needs at least {required}"
        )

    seed = derive_seed(config.base_seed, "splits", dataset.data_hash, holdout_size, folds)
    generator = np.random.default_rng(seed)
    shuffled = list(generator.permutation(equipment))

    holdout = sorted(str(e) for e in shuffled[:holdout_size])
    development = sorted(str(e) for e in shuffled[holdout_size:])

    # Deal development engines round-robin so fold sizes differ by at most one.
    fold_members: list[list[str]] = [[] for _ in range(folds)]
    for index, equipment_id in enumerate(development):
        fold_members[index % folds].append(equipment_id)

    assignment = SplitAssignment(
        holdout=holdout,
        development=development,
        folds=[sorted(members) for members in fold_members],
        seed=seed,
        config_fingerprint=config.fingerprint(),
    )
    validate_splits(assignment)
    return assignment


def validate_splits(splits: SplitAssignment) -> None:
    """Assert the partitions are disjoint and complete."""
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
            f"folds do not cover development exactly (missing {sorted(missing)}, "
            f"unexpected {sorted(extra)})"
        )
    if any(not fold for fold in splits.folds):
        raise ValueError("every fold must contain at least one engine")


def fold_pairs(splits: SplitAssignment) -> list[tuple[list[str], list[str]]]:
    """``(train_engines, validation_engines)`` for each grouped fold."""
    development = list(splits.development)
    pairs: list[tuple[list[str], list[str]]] = []
    for fold in splits.folds:
        validation = set(fold)
        train = [e for e in development if e not in validation]
        pairs.append((train, sorted(validation)))
    return pairs
