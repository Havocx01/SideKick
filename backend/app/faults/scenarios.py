"""Bounded measurement-corruption scenarios, separate from legacy protocols."""
from dataclasses import dataclass, replace
import hashlib
import json

import numpy as np
from pydantic import ConfigDict, Field, model_validator

from app.config import ExperimentConfig
from app.faults.inject import apply_fault
from app.schemas import FaultDuration, FaultKind, FaultSpec, Strict


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class FaultComponent(FaultSpec):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    sensor: str = Field(min_length=1, max_length=128)
    onset_before_failure: int | None = Field(default=None, ge=1, le=100000, strict=True)
    severity_sd: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    sign: int | None = Field(default=None, strict=True)
    ramp_cycles: int | None = Field(default=None, ge=1, le=100000, strict=True)
    length: int | None = Field(default=None, ge=1, le=100000, strict=True)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1, strict=True)

    @model_validator(mode="after")
    def explicit_parameters(self):
        if not self.sensor.strip():
            raise ValueError("Name a sensor")
        if self.onset_before_failure is None and self.seed is None:
            raise ValueError("Random onset needs an explicit seed")
        if self.onset_before_failure is not None and self.seed is not None:
            raise ValueError("An explicit onset does not use a random seed")
        if (self.duration == FaultDuration.transient) != (self.length is not None):
            raise ValueError("Only transient faults require an explicit positive length")
        if self.kind == FaultKind.drift:
            if self.severity_sd is None or self.sign not in (-1, 1) or self.ramp_cycles is None:
                raise ValueError("Drift needs severity, direction and ramp length")
        elif any(value is not None for value in (self.severity_sd, self.sign, self.ramp_cycles)):
            raise ValueError("Only drift faults use severity, direction or ramp length")
        return self


class FaultCase(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(default=1, ge=1, le=1)
    components: tuple[FaultComponent, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def independent_sensors(self):
        sensors = [atom.sensor for atom in self.components]
        if len(sensors) != len(set(sensors)):
            raise ValueError("Only one fault per sensor is supported; same-sensor overlap is undefined")
        object.__setattr__(self, "components", tuple(sorted(self.components, key=lambda atom: atom.sensor)))
        return self

    @property
    def scenario_id(self) -> str:
        # Legacy labels round floats for display. New search/cache identities
        # must retain the complete parameter values even for single components.
        prefix = "single-v1-" if len(self.components) == 1 else "compound-v1-"
        return prefix + fingerprint(self.model_dump(mode="json"))[:24]


class FaultPolicy(Strict):
    """Declared prototype bounds; these do not certify physical plausibility."""
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    allowed_sensors: tuple[str, ...] = Field(min_length=1, max_length=128)
    allowed_groups: tuple[tuple[str, ...], ...] = Field(default=(), max_length=128)
    max_components: int = Field(default=2, ge=1, le=4, strict=True)
    max_severity_sd: float = Field(default=3.0, gt=0, le=100)
    max_duration: int = Field(default=120, ge=1, le=10000, strict=True)
    max_onset: int = Field(default=500, ge=1, le=100000, strict=True)
    max_histories: int = Field(default=256, ge=1, le=1000, strict=True)
    max_rows: int = Field(default=200000, ge=1, le=1000000, strict=True)
    max_evaluations: int = Field(default=32, ge=1, le=128, strict=True)
    max_seconds: float = Field(default=30, gt=0, le=300)
    assumptions: str = Field(default="Independent bounded measurement corruptions; prototype bounds are not equipment-validated.",
        min_length=1, max_length=2000)

    @model_validator(mode="after")
    def known_groups(self):
        if len(set(self.allowed_sensors)) != len(self.allowed_sensors) or any(not s.strip() for s in self.allowed_sensors):
            raise ValueError("Allowed sensors must be unique nonempty names")
        if any(not group or not set(group) <= set(self.allowed_sensors) for group in self.allowed_groups):
            raise ValueError("Allowed groups must contain known sensors")
        return self

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.model_dump(mode="json"))

    def check(self, case: FaultCase, config: ExperimentConfig):
        if len(case.components) > self.max_components:
            raise ValueError("Scenario exceeds the component budget")
        sensors = {atom.sensor for atom in case.components}
        if not sensors <= set(self.allowed_sensors):
            raise ValueError("Scenario uses a sensor outside the allowed mapping")
        if self.allowed_groups and not any(sensors <= set(group) for group in self.allowed_groups):
            raise ValueError("Sensor combination is outside the declared groups")
        for atom in case.components:
            if atom.onset_before_failure is not None and not config.min_useful_lead <= atom.onset_before_failure <= self.max_onset:
                raise ValueError("Scenario onset is outside the declared bounds")
            if atom.severity_sd is not None and atom.severity_sd > self.max_severity_sd:
                raise ValueError("Scenario drift severity exceeds the declared bound")
            if (atom.length or 0) > self.max_duration or (atom.ramp_cycles or 0) > self.max_duration:
                raise ValueError("Scenario duration or ramp exceeds the declared bound")


class ComponentApplication(Strict):
    sensor: str
    onset_index: int
    affected_cycles: int


@dataclass(frozen=True)
class CaseApplication:
    values: np.ndarray | None
    applied: bool
    components: tuple[ComponentApplication, ...]
    reasons: tuple[str, ...]


def apply_case(raw: np.ndarray, rul: np.ndarray, case: FaultCase, builder, config: ExperimentConfig) -> CaseApplication:
    """Independent channels use the same clean input; incomplete cases are atomic."""
    raw = np.asarray(raw, dtype=np.float64)
    if raw.ndim != 2 or raw.shape != (len(rul), len(builder.sensors)):
        raise ValueError("Sensor matrix does not match the history and preprocessing")
    changed, applications, reasons = {}, [], []
    for atom in case.components:
        if atom.sensor not in builder.sensors:
            reasons.append(f"{atom.sensor}: sensor not present")
            continue
        index = builder.preprocessor.index_of(atom.sensor)
        # Legacy injection treats seed=0 as falsy. Set its fallback seed explicitly
        # for new cases without changing historical single-fault behavior.
        injection_config = replace(config, base_seed=atom.seed) if atom.onset_before_failure is None else config
        injected = apply_fault(raw[:, index], rul, atom, sensor_std=builder.preprocessor.std_of(atom.sensor), config=injection_config)
        if not injected.applied:
            reasons.append(f"{atom.sensor}: {injected.reason}")
        elif np.array_equal(raw[:, index], injected.values, equal_nan=True):
            reasons.append(f"{atom.sensor}: no readings changed")
        else:
            changed[index] = injected.values
            applications.append(ComponentApplication(sensor=atom.sensor, onset_index=injected.onset_index, affected_cycles=injected.affected_cycles))
    if reasons:
        return CaseApplication(None, False, (), tuple(reasons))
    values = raw.copy()
    for index, column in changed.items():
        values[:, index] = column
    return CaseApplication(values, True, tuple(applications), ())
