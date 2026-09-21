"""Scenario matrix generation.

Two sets, reported separately and never pooled:

**Required set.** Deliberately timed persistent faults on every varying sensor at
the earlier onset. Model selection uses only this set, so the selection rule is
defined over a fixed, bounded list of cases decided before any result is seen.

**Full set.** Both onsets, both drift signs, both drift severities, plus the
shorter transient variants. Reported as supporting evidence.

**Random-onset set.** A seeded sensitivity check on whether the findings depend on
where the fault was placed. Reported separately again; it is not evidence about
how often faults occur.
"""

from __future__ import annotations

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import FaultDuration, FaultKind, FaultSpec
from app.utils.determinism import derive_seed


def required_scenarios(
    sensors: list[str], config: ExperimentConfig = EXPERIMENT
) -> list[FaultSpec]:
    """The bounded set used for model selection.

    Per sensor: dropout, stuck reading, and drift in both directions at the lower
    severity, all persistent, all beginning at the earlier onset. Drift is
    included in both directions because a one-sided test would let a model pass by
    being insensitive in one direction only.
    """
    onset = max(config.fault_onsets)
    severity = min(config.drift_severities)
    specs: list[FaultSpec] = []
    for sensor in sensors:
        specs.append(
            FaultSpec(
                kind=FaultKind.dropout,
                duration=FaultDuration.persistent,
                sensor=sensor,
                onset_before_failure=onset,
            )
        )
        specs.append(
            FaultSpec(
                kind=FaultKind.stuck,
                duration=FaultDuration.persistent,
                sensor=sensor,
                onset_before_failure=onset,
            )
        )
        for sign in config.drift_signs:
            specs.append(
                FaultSpec(
                    kind=FaultKind.drift,
                    duration=FaultDuration.persistent,
                    sensor=sensor,
                    onset_before_failure=onset,
                    severity_sd=severity,
                    sign=sign,
                    ramp_cycles=config.drift_ramp_cycles,
                )
            )
    return specs


def full_scenarios(
    sensors: list[str],
    config: ExperimentConfig = EXPERIMENT,
    *,
    include_transient: bool = True,
) -> list[FaultSpec]:
    """Every reported scenario, required set included."""
    specs: list[FaultSpec] = []
    for sensor in sensors:
        for onset in config.fault_onsets:
            specs.append(
                FaultSpec(
                    kind=FaultKind.dropout,
                    duration=FaultDuration.persistent,
                    sensor=sensor,
                    onset_before_failure=onset,
                )
            )
            specs.append(
                FaultSpec(
                    kind=FaultKind.stuck,
                    duration=FaultDuration.persistent,
                    sensor=sensor,
                    onset_before_failure=onset,
                )
            )
            for severity in config.drift_severities:
                for sign in config.drift_signs:
                    specs.append(
                        FaultSpec(
                            kind=FaultKind.drift,
                            duration=FaultDuration.persistent,
                            sensor=sensor,
                            onset_before_failure=onset,
                            severity_sd=severity,
                            sign=sign,
                            ramp_cycles=config.drift_ramp_cycles,
                        )
                    )
            if include_transient:
                for kind in (FaultKind.dropout, FaultKind.stuck):
                    specs.append(
                        FaultSpec(
                            kind=kind,
                            duration=FaultDuration.transient,
                            sensor=sensor,
                            onset_before_failure=onset,
                            length=config.transient_length,
                        )
                    )
    return _deduplicate(specs)


def random_onset_scenarios(
    sensors: list[str],
    config: ExperimentConfig = EXPERIMENT,
    *,
    repeats: int = 3,
) -> list[FaultSpec]:
    """Seeded random-onset variants for the timing-sensitivity check."""
    specs: list[FaultSpec] = []
    for sensor in sensors:
        for kind in (FaultKind.dropout, FaultKind.stuck):
            for repeat in range(repeats):
                specs.append(
                    FaultSpec(
                        kind=kind,
                        duration=FaultDuration.persistent,
                        sensor=sensor,
                        onset_before_failure=None,
                        seed=derive_seed(config.base_seed, "random_onset", sensor, kind.value, repeat),
                    )
                )
    return specs


def _deduplicate(specs: list[FaultSpec]) -> list[FaultSpec]:
    seen: set[str] = set()
    unique: list[FaultSpec] = []
    for spec in specs:
        key = spec.scenario_id
        if key not in seen:
            seen.add(key)
            unique.append(spec)
    return unique


def describe_matrix(
    sensors: list[str], config: ExperimentConfig = EXPERIMENT
) -> dict[str, int]:
    """Scenario counts, used by the runtime spike and reported in the evidence."""
    required = required_scenarios(sensors, config)
    full = full_scenarios(sensors, config)
    random_onset = random_onset_scenarios(sensors, config)
    return {
        "sensors": len(sensors),
        "required": len(required),
        "full": len(full),
        "random_onset": len(random_onset),
    }
