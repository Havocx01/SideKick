"""Frozen experiment definition and runtime settings.

``ExperimentConfig`` is the experiment. Every number the prototype reports is
produced under one of these, and its ``fingerprint`` is written into every run
record. Changing a field changes the fingerprint, which is how a reviewer can
tell that a reported metric and a frozen configuration belong together.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]

RunMode = Literal["full", "replay"]


@dataclass(frozen=True)
class ExperimentConfig:
    """The experiment definition from the idea-phase proposal.

    Cycle conventions: ``rul`` is the remaining useful life measured in cycles,
    defined as ``failure_cycle - current_cycle``. The failure cycle itself
    (``rul == 0``) is excluded from both training and scoring.
    """

    # --- Prediction target -------------------------------------------------
    horizon_cycles: int = 30
    """Positive label when 1 <= rul <= horizon_cycles."""

    exclude_failure_cycle: bool = True

    # --- Features ----------------------------------------------------------
    feature_window: int = 20
    """Current reading plus the preceding 19 cycles."""

    # --- Partitions --------------------------------------------------------
    holdout_engines: int = 20
    """Reserved for a single frozen final evaluation."""

    n_folds: int = 5
    """Grouped folds over the remaining development engines."""

    configs_per_candidate: int = 3

    # --- Alert logic -------------------------------------------------------
    alert_on_consecutive: int = 2
    """Scores at or above threshold needed to open an episode."""

    alert_off_consecutive: int = 2
    """Scores below threshold needed to close an episode."""

    # --- Operational measures ---------------------------------------------
    min_useful_lead: int = 10
    """An alert must be active no later than this many cycles before failure."""

    late_window_end: int = 9
    """An alert appearing only inside this many cycles is late, not useful."""

    transition_band_end: int = 45
    """Cycles 31..45 are excluded from the early alarm burden denominator."""

    # --- Fault tests -------------------------------------------------------
    fault_onsets: tuple[int, ...] = (60, 30)
    """Cycles before failure at which a persistent fault begins."""

    transient_length: int = 10
    drift_ramp_cycles: int = 20
    drift_severities: tuple[float, ...] = (1.0, 2.0)
    drift_signs: tuple[int, ...] = (-1, 1)

    # --- Determinism -------------------------------------------------------
    base_seed: int = 20260918

    # --- Acceptance criteria defaults -------------------------------------
    # The engineer sets these before selection. These are the demo defaults and
    # are recorded alongside results rather than treated as universal.
    min_detection_fraction: float = 0.70
    max_early_alarm_burden: float = 0.10

    @property
    def max_useful_lead(self) -> int:
        """Upper edge of the useful warning window, tied to the horizon."""
        return self.horizon_cycles

    def as_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable hash of the experiment definition."""
        payload = json.dumps(self.as_dict(), sort_keys=True, default=list)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def validate(self) -> None:
        """Fail fast on internally inconsistent settings."""
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
        if min(self.fault_onsets) < self.min_useful_lead:
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
    """Runtime settings. These do not affect reported numbers."""

    mode: RunMode = field(
        default_factory=lambda: "replay" if os.environ.get("SIDEKICK_MODE") == "replay" else "full"
    )
    data_dir: Path = field(default_factory=lambda: _env_path("SIDEKICK_DATA_DIR", REPO_ROOT / "data"))
    artifacts_dir: Path = field(
        default_factory=lambda: _env_path("SIDEKICK_ARTIFACTS_DIR", REPO_ROOT / "artifacts")
    )
    bundle_path: Path = field(
        default_factory=lambda: _env_path(
            "SIDEKICK_BUNDLE_PATH", REPO_ROOT / "evidence" / "bundle.json"
        )
    )
    mlflow_enabled: bool = field(default_factory=lambda: _env_bool("SIDEKICK_MLFLOW", True))
    mlflow_uri: str = field(
        default_factory=lambda: os.environ.get("MLFLOW_TRACKING_URI", f"file:{REPO_ROOT / 'mlruns'}")
    )

    llm_model: str = field(default_factory=lambda: os.environ.get("SIDEKICK_LLM_MODEL", "gpt-5.4-mini"))
    llm_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    llm_max_tool_calls: int = field(
        default_factory=lambda: int(os.environ.get("SIDEKICK_MAX_TOOL_CALLS", "8"))
    )
    llm_timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("SIDEKICK_LLM_TIMEOUT", "60"))
    )

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get(
                "SIDEKICK_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        )
    )

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
    def llm_available(self) -> bool:
        return bool(self.llm_api_key)

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.artifacts_dir, self.runs_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)


EXPERIMENT = ExperimentConfig()
EXPERIMENT.validate()

_settings: Settings | None = None


def get_settings() -> Settings:
    """Process-wide settings, read from the environment once."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Drop cached settings. Used by tests that patch the environment."""
    global _settings
    _settings = None
