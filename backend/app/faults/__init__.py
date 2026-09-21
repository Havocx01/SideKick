"""Sensor-fault specification, injection and scenario matrix."""

from app.faults.inject import InjectionResult, apply_fault, resolve_onset
from app.faults.matrix import (
    describe_matrix,
    full_scenarios,
    random_onset_scenarios,
    required_scenarios,
)

__all__ = [
    "InjectionResult",
    "apply_fault",
    "describe_matrix",
    "full_scenarios",
    "random_onset_scenarios",
    "required_scenarios",
    "resolve_onset",
]
