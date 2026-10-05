"""Frozen experiment definition and runtime settings."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]

RunMode = Literal["full", "replay", "demo"]


@dataclass(frozen=True)
class ExperimentConfig:
    """Failure-cycle readings are excluded from training and scoring."""

    protocol_revision: int = 3
    """Revision 3 fingerprints failure targets, confirmed mapping and actual criteria."""

    horizon_cycles: int = 30
    """Positive label when 1 <= rul <= horizon_cycles."""

    exclude_failure_cycle: bool = True

    feature_window: int = 20
    """Current reading plus the preceding 19 cycles."""

    holdout_engines: int = 20
    """Reserved for a single frozen final evaluation."""

    n_folds: int = 5
    """Grouped folds over the remaining development engines."""

    configs_per_candidate: int = 3

    alert_on_consecutive: int = 2
    """Scores at or above threshold needed to open an episode."""

    alert_off_consecutive: int = 2
    """Scores below threshold needed to close an episode."""

    min_useful_lead: int = 10
    """An alert must be active no later than this many cycles before failure."""

    late_window_end: int = 9
    """An alert appearing only inside this many cycles is late, not useful."""

    transition_band_end: int = 45
    """Cycles 31..45 are excluded from the early alarm burden denominator."""

    fault_onsets: tuple[int, ...] = (60, 30)
    """Cycles before failure at which a persistent fault begins."""

    transient_length: int = 10
    drift_ramp_cycles: int = 20
    drift_severities: tuple[float, ...] = (1.0, 2.0)
    drift_signs: tuple[int, ...] = (-1, 1)

    base_seed: int = 20260918

    # Demonstration defaults; each experiment records the limits chosen before training.
    min_detection_fraction: float = 0.70
    max_early_alarm_burden: float = 0.10
    fault_scenarios: tuple[dict, ...] | None = None

    @property
    def max_useful_lead(self) -> int:
        return self.horizon_cycles

    def as_dict(self) -> dict:
        result = asdict(self)
        if self.protocol_revision < 4 and self.fault_scenarios is None:
            result.pop("fault_scenarios")
        return result

    def fingerprint(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, default=list)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def validate(self) -> None:
        if not 0 <= self.min_detection_fraction <= 1 or not 0 <= self.max_early_alarm_burden <= 1:
            raise ValueError("Acceptance criteria must be finite fractions between 0 and 1")
        if not 0 < self.min_useful_lead < self.horizon_cycles:
            raise ValueError("min_useful_lead must sit inside the horizon")
        if self.late_window_end >= self.min_useful_lead:
            raise ValueError("late window must end before the useful window opens")
        if self.transition_band_end <= self.horizon_cycles:
            raise ValueError("transition band must extend beyond the horizon")
        if self.feature_window < 2:
            raise ValueError("feature_window must cover at least two cycles")
        if self.n_folds < 2:
            raise ValueError("n_folds must be at least 2")
        if self.fault_scenarios is None and min(self.fault_onsets) < self.min_useful_lead:
            raise ValueError("a fault onset inside the useful window cannot be scored")


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    mode: RunMode = field(default_factory=lambda: os.environ.get("SIDEKICK_MODE", "full"))

    data_dir: Path = field(default_factory=lambda: _env_path("SIDEKICK_DATA_DIR", REPO_ROOT / "data"))
    artifacts_dir: Path = field(default_factory=lambda: _env_path("SIDEKICK_ARTIFACTS_DIR", REPO_ROOT / "artifacts"))
    bundle_path: Path = field(
        default_factory=lambda: _env_path("SIDEKICK_BUNDLE_PATH", REPO_ROOT / "evidence" / "bundle.json")
    )
    mlflow_enabled: bool = field(default_factory=lambda: _env_bool("SIDEKICK_MLFLOW", True))
    mlflow_uri: str = field(
        default_factory=lambda: os.environ.get("MLFLOW_TRACKING_URI", f"file:{REPO_ROOT / 'mlruns'}")
    )

    llm_max_tool_calls: int = field(default_factory=lambda: int(os.environ.get("SIDEKICK_MAX_TOOL_CALLS", "8")))

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get("SIDEKICK_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        )
    )

    def __post_init__(self):
        if self.mode not in ("full", "replay", "demo"):
            raise ValueError("SIDEKICK_MODE must be full, replay or demo")

    @property
    def runs_dir(self) -> Path:
        return self.artifacts_dir / "runs"

    @property
    def exports_dir(self) -> Path:
        return self.artifacts_dir / "exports"

    @property
    def cmapss_dir(self) -> Path:
        return self.data_dir / "cmapss"

    @property
    def static_dir(self) -> Path:
        return _env_path("SIDEKICK_STATIC_DIR", REPO_ROOT / "frontend" / "dist")

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.artifacts_dir, self.runs_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


EXPERIMENT = ExperimentConfig()
EXPERIMENT.validate()

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
