"""Reproducible sensor-fault injection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import FaultDuration, FaultKind, FaultSpec


@dataclass(frozen=True)
class InjectionResult:
    values: np.ndarray
    applied: bool
    onset_index: int | None = None
    affected_cycles: int = 0
    reason: str | None = None


def resolve_onset(rul: np.ndarray, spec: FaultSpec, config: ExperimentConfig) -> tuple[int | None, str | None]:
    """Return None when the requested onset falls before the recorded history."""
    rul = np.asarray(rul, dtype=int)
    if rul.size == 0:
        return None, "history is empty"

    if spec.onset_before_failure is not None:
        target = int(spec.onset_before_failure)
        # Moving an unreachable onset to the first cycle would change the scenario.
        if target > int(rul.max()):
            return None, f"history never reaches {target} cycles before failure"
        index = int(np.flatnonzero(rul <= target)[0])
    else:
        # Keep random onsets close enough to overlap the decision window.
        generator = np.random.default_rng(spec.seed or config.base_seed)
        lowest = (
            int(np.flatnonzero(rul <= config.transition_band_end)[0])
            if (rul <= config.transition_band_end).any()
            else 0
        )
        highest = max(lowest, rul.size - 1)
        index = int(generator.integers(lowest, highest + 1)) if highest > lowest else lowest

    # Leave at least one cycle before the fault so "stuck" has a value to hold.
    if index == 0:
        index = 1 if rul.size > 1 else 0
    if index >= rul.size:
        return None, "onset falls past the end of the history"
    return index, None


def _extent(values_length: int, onset: int, spec: FaultSpec, config: ExperimentConfig) -> slice:
    if spec.duration == FaultDuration.transient:
        length = int(spec.length or config.transient_length)
        return slice(onset, min(values_length, onset + length))
    return slice(onset, values_length)


def apply_fault(
    values: np.ndarray, rul: np.ndarray, spec: FaultSpec, *, sensor_std: float, config: ExperimentConfig = EXPERIMENT
) -> InjectionResult:
    """Drift is scaled by the training standard deviation, not the corrupted history."""
    values = np.asarray(values, dtype=np.float64)
    onset, reason = resolve_onset(rul, spec, config)
    if onset is None:
        return InjectionResult(values=values.copy(), applied=False, reason=reason)

    span = _extent(values.shape[0], onset, spec, config)
    if span.stop <= span.start:
        return InjectionResult(values=values.copy(), applied=False, reason="empty fault span")

    corrupted = values.copy()

    if spec.kind == FaultKind.dropout:
        # Downstream imputation uses the training median and retains a missingness feature.
        corrupted[span] = np.nan

    elif spec.kind == FaultKind.stuck:
        held = corrupted[span.start - 1] if span.start > 0 else corrupted[span.start]
        if not np.isfinite(held):
            finite = np.flatnonzero(np.isfinite(corrupted[: span.start]))
            if finite.size == 0:
                return InjectionResult(values=corrupted, applied=False, reason="no finite reading to hold")
            held = corrupted[finite[-1]]
        corrupted[span] = held

    elif spec.kind == FaultKind.drift:
        severity = float(spec.severity_sd if spec.severity_sd is not None else 1.0)
        sign = int(spec.sign if spec.sign is not None else 1)
        magnitude = sign * severity * float(sensor_std)
        if sensor_std <= 0.0:
            return InjectionResult(values=corrupted, applied=False, reason="sensor has no training variation")
        rampLength = int(spec.ramp_cycles or config.drift_ramp_cycles)
        affected = np.arange(span.start, span.stop)
        # Ramp linearly to full magnitude, then hold it. Drift does not heal.
        progress = np.clip((affected - span.start + 1) / max(rampLength, 1), 0.0, 1.0)
        corrupted[span] = corrupted[span] + magnitude * progress

    else:  # pragma: no cover - the enum is closed
        raise ValueError(f"unsupported fault kind {spec.kind!r}")

    return InjectionResult(
        values=corrupted, applied=True, onset_index=onset, affected_cycles=int(span.stop - span.start)
    )
