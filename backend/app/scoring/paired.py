"""Exploratory paired comparisons resample whole equipment histories."""

import numpy as np

from app.schemas import PairedComparison
from app.utils.determinism import derive_seed


def compare(result, first, second, kind):
    matrix = result.matrix.equipment_metrics
    scenarios = sorted(result.required_scenario_ids)
    equipment = sorted(result.training.splits.development)
    tables = []
    for name in (first, second):
        columns = []
        for scenario in scenarios:
            rows = {s.outcome.equipment_id: s for s in matrix.get((name, scenario), [])}
            if set(rows) != set(equipment):
                return None
            columns.append(np.array([[float(rows[e].outcome.detected), rows[e].alarm_eligible_cycles,
                                      rows[e].eligible_cycles] for e in equipment]))
        if not columns:
            return None
        tables.append(np.stack(columns, axis=1))
    a, b = tables
    seed = derive_seed(result.training.config.base_seed, "paired", first, second)
    indices = np.random.default_rng(seed).integers(0, len(equipment), (1000, len(equipment)))
    detection = (b[:, :, 0] - a[:, :, 0]).mean(axis=1)
    delta = detection[indices].mean(axis=1)

    def burden(table):
        eligible = table[:, :, 2].sum(axis=0)
        return float(np.mean(table[:, :, 1].sum(axis=0) / eligible)) if np.all(eligible > 0) else None

    original_a, original_b = burden(a), burden(b)
    burden_deltas = []
    if original_a is not None and original_b is not None:
        for row in indices:
            x, y = burden(a[row]), burden(b[row])
            if x is not None and y is not None:
                burden_deltas.append(y - x)
    return PairedComparison(
        first=first, second=second, kind=kind, engines=len(equipment), scenarios=len(scenarios), seed=seed,
        detection_delta=float(detection.mean()), detection_interval=np.quantile(delta, [.025, .975]).tolist(),
        burden_delta=original_b - original_a if original_a is not None and original_b is not None else None,
        burden_interval=np.quantile(burden_deltas, [.025, .975]).tolist() if len(burden_deltas) == 1000 else None,
    )


def paired_comparisons(result):
    pairs = []
    qualifying = [v for v in result.selection.ranked if v.qualifies]
    names = [f"{v.candidate.value}/{v.config_id}" for v in qualifying]
    if len(names) > 1:
        pairs.append((names[0], names[1], "selected"))
    plain = next((n for n in names if n.startswith("xgboost/")), None)
    augmented = next((n for n in names if n.startswith("xgboost_augmented/")), None)
    if plain and augmented and (plain, augmented, "selected") not in pairs:
        pairs.append((plain, augmented, "selected"))
    for name in result.training.specs:
        if name.startswith("xgboost/xgb"):
            partner = name.replace("xgboost/xgb", "xgboost_augmented/aug")
            if partner in result.training.specs:
                pairs.append((name, partner, "matched_augmentation"))
    return [item for first, second, kind in pairs if (item := compare(result, first, second, kind)) is not None]
