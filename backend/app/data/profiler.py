"""Dataset profiling and quality assessment."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import ExperimentConfig
from app.data.contract import CANONICAL_CYCLE, CANONICAL_EQUIPMENT, looks_like_hours
from app.data.dataset import Dataset
from app.schemas import DatasetProfile, ProfileFinding, SensorProfile, Severity

# Drift and stuck-sensor tests need enough distinct readings to be meaningful.
MIN_DISTINCT_FOR_FAULTS = 3


def _sensor_profiles(dataset: Dataset) -> list[SensorProfile]:
    profiles: list[SensorProfile] = []
    for sensor in dataset.sensors:
        values = dataset.frame[sensor]
        finite = values.dropna()
        distinct = int(finite.nunique())
        std = float(finite.std(ddof=0)) if len(finite) > 1 else 0.0
        constant = distinct <= 1
        profiles.append(
            SensorProfile(
                name=sensor,
                mean=float(finite.mean()) if len(finite) else None,
                std=std if len(finite) > 1 else None,
                minimum=float(finite.min()) if len(finite) else None,
                maximum=float(finite.max()) if len(finite) else None,
                missing_fraction=float(values.isna().mean()),
                constant=constant,
                varies=(not constant) and std > 0.0 and distinct >= MIN_DISTINCT_FOR_FAULTS,
            )
        )
    return profiles


def profile_dataset(dataset: Dataset, *, config: ExperimentConfig | None = None) -> DatasetProfile:
    config = config or dataset.config
    frame = dataset.frame
    findings: list[ProfileFinding] = []

    equipmentIds = dataset.equipment_ids
    lifetimes = dataset.lifetimes
    sensors = _sensor_profiles(dataset)

    duplicated = frame.duplicated(subset=[CANONICAL_EQUIPMENT, CANONICAL_CYCLE], keep=False)
    if bool(duplicated.any()):
        offenders = frame.loc[duplicated, [CANONICAL_EQUIPMENT, CANONICAL_CYCLE]].head(10).to_dict("records")
        findings.append(
            ProfileFinding(
                code="DUPLICATE_READINGS",
                severity=Severity.blocker,
                message=(
                    f"{int(duplicated.sum())} rows share an equipment ID and cycle. "
                    "Each cycle must appear once per piece of equipment."
                ),
                detail={"examples": offenders},
            )
        )

    diffs = frame.groupby(CANONICAL_EQUIPMENT, sort=False)[CANONICAL_CYCLE].diff()
    within = diffs.dropna()
    if bool((within <= 0).any()):
        findings.append(
            ProfileFinding(
                code="UNORDERED_CYCLES",
                severity=Severity.warning,
                message=(
                    "Cycle indices do not increase strictly within every history. "
                    "Rows were sorted on load; check the source ordering."
                ),
                detail={"non_increasing_steps": int((within <= 0).sum())},
            )
        )
    gaps = int((within > 1).sum())
    if gaps:
        findings.append(
            ProfileFinding(
                code="CYCLE_GAPS",
                severity=Severity.warning,
                message=(
                    f"{gaps} gaps in the cycle index. Trailing windows treat the "
                    "readings as consecutive, so gaps widen the real time span of a "
                    "window."
                ),
                detail={"gap_steps": gaps, "largest_gap": int(within.max())},
            )
        )

    missing = {s.name: s.missing_fraction for s in sensors if s.missing_fraction > 0}
    if missing:
        worst = max(missing.values())
        findings.append(
            ProfileFinding(
                code="MISSING_VALUES",
                severity=Severity.blocker if worst > 0.5 else Severity.warning,
                message=(
                    f"{len(missing)} channels contain missing readings "
                    f"(worst {worst:.1%}). Gaps are filled with training medians and "
                    "flagged, which is also how injected dropout is handled."
                ),
                detail={"per_channel": {k: round(v, 4) for k, v in sorted(missing.items())}},
            )
        )

    constant = [s.name for s in sensors if s.constant]
    if constant:
        findings.append(
            ProfileFinding(
                code="CONSTANT_CHANNELS",
                severity=Severity.info,
                message=(
                    f"{len(constant)} channels never change and carry no degradation "
                    "signal. They stay as model inputs but are not fault-tested."
                ),
                detail={"channels": constant},
            )
        )

    varying = [s.name for s in sensors if s.varies]
    findings.append(
        ProfileFinding(
            code="FAULT_ELIGIBLE_CHANNELS",
            severity=Severity.info,
            message=f"{len(varying)} channels vary and are eligible for fault testing.",
            detail={"channels": varying},
        )
    )
    if not varying:
        findings.append(
            ProfileFinding(
                code="NO_FAULT_ELIGIBLE_CHANNELS",
                severity=Severity.blocker,
                message="No channel varies, so no sensor fault can be simulated.",
                detail={},
            )
        )

    hourLike = [c for c in [dataset.mapping.cycle_index, *dataset.mapping.ignored] if looks_like_hours(str(c))]
    if hourLike:
        findings.append(
            ProfileFinding(
                code="HOURS_BASED_TIME",
                severity=Severity.warning,
                message=(
                    "Time appears to be recorded in hours. Every horizon, lead time "
                    "and fault onset in this build is counted in operating cycles, "
                    "and cycles are not converted to hours."
                ),
                detail={"columns": [str(c) for c in hourLike]},
            )
        )

    needed = config.holdout_engines + config.n_folds
    if len(equipmentIds) < 2:
        findings.append(
            ProfileFinding(
                code="SINGLE_EQUIPMENT",
                severity=Severity.blocker,
                message=(
                    "Only one piece of equipment is present. Evaluating on unseen "
                    "equipment needs at least two, and the reported protocol needs "
                    f"at least {needed}."
                ),
                detail={"equipment_count": len(equipmentIds)},
            )
        )
    elif len(equipmentIds) < needed:
        findings.append(
            ProfileFinding(
                code="INSUFFICIENT_EQUIPMENT",
                severity=Severity.blocker,
                message=(
                    f"{len(equipmentIds)} histories cannot support a "
                    f"{config.holdout_engines}-engine holdout plus {config.n_folds} "
                    f"grouped folds, which needs at least {needed}."
                ),
                detail={"equipment_count": len(equipmentIds), "required": needed},
            )
        )

    minUseful = config.feature_window + config.horizon_cycles
    short = {k: v for k, v in lifetimes.items() if v < minUseful}
    if short:
        findings.append(
            ProfileFinding(
                code="SHORT_HISTORIES",
                severity=Severity.warning if len(short) < len(lifetimes) else Severity.blocker,
                message=(
                    f"{len(short)} histories are shorter than {minUseful} cycles, "
                    f"which is the {config.feature_window}-cycle warm-up plus the "
                    f"{config.horizon_cycles}-cycle horizon. They contribute few or "
                    "no scorable cycles."
                ),
                detail={"shortest": min(short.values()), "count": len(short)},
            )
        )

    if dataset.mapping.failure_cycle is None:
        findings.append(
            ProfileFinding(
                code="ASSUMED_COMPLETE_HISTORIES",
                severity=Severity.info,
                message=(
                    "No failure-cycle column was supplied, so each history is "
                    "treated as complete and its last cycle is taken as the failure "
                    "cycle. Censored histories need a separate protocol."
                ),
                detail={},
            )
        )

    labels = dataset.label_vector()
    scorable = dataset.scorable_mask()
    scorableLabels = labels[scorable]
    positiveFraction = float(scorableLabels.mean()) if scorableLabels.size else None

    if not scorableLabels.size:
        findings.append(
            ProfileFinding(
                code="NO_SCORABLE_CYCLES",
                severity=Severity.blocker,
                message=("No cycle survives the warm-up period, so there is nothing to train on or score."),
                detail={},
            )
        )
    else:
        enginesWithPositives = int(
            pd.Series(labels[scorable]).groupby(frame.loc[scorable, CANONICAL_EQUIPMENT].to_numpy()).max().sum()
        )
        findings.append(
            ProfileFinding(
                code="LABEL_COVERAGE",
                severity=Severity.info if positiveFraction else Severity.blocker,
                message=(
                    f"{positiveFraction:.1%} of scorable cycles fall inside the "
                    f"{config.horizon_cycles}-cycle horizon; "
                    f"{enginesWithPositives} of {len(equipmentIds)} histories "
                    "contain at least one positive cycle."
                ),
                detail={
                    "positive_fraction": round(positiveFraction, 5),
                    "engines_with_positives": enginesWithPositives,
                    "scorable_cycles": int(scorable.sum()),
                },
            )
        )

    lifetimeValues = np.array(list(lifetimes.values()), dtype=float)
    usable = not any(f.severity == Severity.blocker for f in findings)

    return DatasetProfile(
        dataset_id=dataset.dataset_id,
        source=dataset.source,
        data_hash=dataset.data_hash,
        row_count=len(frame),
        equipment_count=len(equipmentIds),
        min_cycles=int(lifetimeValues.min()) if lifetimeValues.size else 0,
        max_cycles=int(lifetimeValues.max()) if lifetimeValues.size else 0,
        median_cycles=float(np.median(lifetimeValues)) if lifetimeValues.size else 0.0,
        sensors=sensors,
        findings=findings,
        positive_label_fraction=positiveFraction,
        usable=usable,
    )


def blockers(profile: DatasetProfile) -> list[ProfileFinding]:
    return [f for f in profile.findings if f.severity == Severity.blocker]
