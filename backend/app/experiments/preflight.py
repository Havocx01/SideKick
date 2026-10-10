"""Admission checks that do not fit models or inspect reserved labels."""

import numpy as np

from app.experiments.exposure import history_ids
from app.faults.augmentation import augmentation_onset_bounds
from app.models.splits import fold_pairs


def validate_histories(dataset):
    """Structural checks apply before a new upload is confirmed or split."""
    ordered = dataset.frame.sort_values(["equipment_id", "cycle"])
    steps = ordered.groupby("equipment_id", sort=False)["cycle"].diff().dropna()
    if (steps != 1).any():
        raise ValueError(
            "Each equipment history must contain consecutive operating cycles, with exactly one reading per cycle. "
            "Supply the missing cycles; empty sensor values are supported, missing cycle rows are not."
        )
    identities = history_ids(dataset, dataset.equipment_ids)
    grouped = {}
    for equipment, identity in identities.items():
        grouped.setdefault(identity, []).append(equipment)
    duplicates = [ids for ids in grouped.values() if len(ids) > 1]
    if duplicates:
        examples = "; ".join(", ".join(ids[:10]) + (", …" if len(ids) > 10 else "") for ids in duplicates[:5])
        raise ValueError(
            f"Repeated readings in equipment histories: {examples}. "
            "Copies cannot count as independent histories. Supply distinct equipment histories."
        )


def check_training_feasibility(dataset, splits):
    """Check the actual development folds using their resolved labels and warm-up."""
    # Subset first: no reserved target or sensor values enter feasibility decisions.
    development = dataset.subset(splits.development)
    scorable = development.scorable_mask()
    labels = development.label_vector()
    ids = development.frame["equipment_id"]
    for index, (training, validation) in enumerate(fold_pairs(splits), start=1):
        training_rows = scorable & ids.isin(training).to_numpy()
        if not training_rows.any():
            raise ValueError(f"Fold {index} training has no scorable readings after feature warm-up. Supply longer complete histories.")
        classes = set(labels[training_rows])
        if classes != {0, 1}:
            missing = "negative class (before the warning horizon)" if 0 not in classes else "positive class (inside the warning horizon)"
            raise ValueError(
                f"Fold {index} training is missing the {missing}. "
                "Supply suitable complete histories or use valid warning timing; both classes are required."
            )
        validation_rows = scorable & ids.isin(validation).to_numpy()
        if not validation_rows.any():
            raise ValueError(f"Fold {index} validation has no scorable readings after feature warm-up. Supply longer complete histories.")
        # Match preprocessing eligibility exactly, without fitting or using reserve data.
        varying = False
        for sensor in development.sensors:
            finite = development.frame.loc[training_rows, sensor].dropna().to_numpy(dtype=float)
            if finite.size and np.std(finite, ddof=0) > 0:
                varying = True
                break
        if varying:
            support = int(development.frame.loc[ids.isin(training)].groupby("equipment_id")["rul"].max().min())
            try:
                augmentation_onset_bounds(development.config, support)
            except ValueError as exc:
                raise ValueError(f"Fold {index}: {exc}") from exc
