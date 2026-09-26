"""Scenario matrix generation."""

from __future__ import annotations

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import FaultDuration, FaultKind, FaultSpec
from app.utils.determinism import derive_seed


def required_scenarios(sensors: list[str], config: ExperimentConfig = EXPERIMENT) -> list[FaultSpec]:
    onset = max(config.fault_onsets)
    severity = min(config.drift_severities)
    specs: list[FaultSpec] = []
    for sensor in sensors:
        specs.append(
            FaultSpec(
                kind=FaultKind.dropout, duration=FaultDuration.persistent, sensor=sensor, onset_before_failure=onset
            )
        )
        specs.append(
            FaultSpec(
                kind=FaultKind.stuck, duration=FaultDuration.persistent, sensor=sensor, onset_before_failure=onset
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
    sensors: list[str], config: ExperimentConfig = EXPERIMENT, *, include_transient: bool = True
) -> list[FaultSpec]:
    specs: list[FaultSpec] = []
    for sensor in sensors:
        for onset in config.fault_onsets:
            specs.append(
                FaultSpec(
                    kind=FaultKind.dropout, duration=FaultDuration.persistent, sensor=sensor, onset_before_failure=onset
                )
            )
            specs.append(
                FaultSpec(
                    kind=FaultKind.stuck, duration=FaultDuration.persistent, sensor=sensor, onset_before_failure=onset
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
    sensors: list[str], config: ExperimentConfig = EXPERIMENT, *, repeats: int = 3
) -> list[FaultSpec]:
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


def describe_matrix(sensors: list[str], config: ExperimentConfig = EXPERIMENT) -> dict[str, int]:
    required = required_scenarios(sensors, config)
    full = full_scenarios(sensors, config)
    randomOnset = random_onset_scenarios(sensors, config)
    return {"sensors": len(sensors), "required": len(required), "full": len(full), "random_onset": len(randomOnset)}
