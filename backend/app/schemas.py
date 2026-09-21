"""The contract shared by the pipeline, the API and the frontend.

These models are the single definition of every shape that crosses a boundary.
``scripts/generate_types.py`` derives the frontend's TypeScript types from them,
so a change here cannot silently diverge from the UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Base model: reject unknown fields so contract drift fails loudly."""

    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ColumnRole(str, Enum):
    equipment_id = "equipment_id"
    cycle_index = "cycle_index"
    sensor = "sensor"
    failure_cycle = "failure_cycle"
    ignored = "ignored"


class FaultKind(str, Enum):
    dropout = "dropout"
    stuck = "stuck"
    drift = "drift"


class FaultDuration(str, Enum):
    persistent = "persistent"
    transient = "transient"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    blocker = "blocker"


class CandidateKind(str, Enum):
    logistic_regression = "logistic_regression"
    xgboost = "xgboost"
    xgboost_augmented = "xgboost_augmented"
    age_baseline = "age_baseline"


class Partition(str, Enum):
    out_of_fold = "out_of_fold"
    holdout = "holdout"


class SelectionOutcome(str, Enum):
    qualified = "qualified"
    none_qualified = "none_qualified"


# ---------------------------------------------------------------------------
# Data contract and profiling
# ---------------------------------------------------------------------------


class ColumnMapping(Strict):
    """How uploaded columns map onto the roles the pipeline requires."""

    equipment_id: str
    cycle_index: str
    sensors: list[str]
    failure_cycle: str | None = None
    ignored: list[str] = Field(default_factory=list)
    inferred: bool = False
    ambiguous: list[str] = Field(
        default_factory=list,
        description="Columns the profiler could not assign confidently. The "
        "engineer confirms these before training.",
    )


class SensorProfile(Strict):
    name: str
    mean: float | None
    std: float | None
    minimum: float | None
    maximum: float | None
    missing_fraction: float
    constant: bool
    varies: bool = Field(description="Eligible for fault testing.")


class ProfileFinding(Strict):
    code: str
    severity: Severity
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(Strict):
    dataset_id: str
    source: str
    data_hash: str
    row_count: int
    equipment_count: int
    min_cycles: int
    max_cycles: int
    median_cycles: float
    sensors: list[SensorProfile]
    findings: list[ProfileFinding] = Field(default_factory=list)
    positive_label_fraction: float | None = None
    usable: bool = True

    @property
    def varying_sensors(self) -> list[str]:
        return [s.name for s in self.sensors if s.varies]


# ---------------------------------------------------------------------------
# Partitions and candidates
# ---------------------------------------------------------------------------


class SplitAssignment(Strict):
    """Engine-level partitions. No engine appears in more than one place."""

    holdout: list[str]
    development: list[str]
    folds: list[list[str]] = Field(description="Validation engines per fold.")
    seed: int
    config_fingerprint: str


class CandidateConfig(Strict):
    candidate: CandidateKind
    config_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    uses_sensors: bool = True
    description: str = ""


# ---------------------------------------------------------------------------
# Faults
# ---------------------------------------------------------------------------


class FaultSpec(Strict):
    """One reproducible sensor fault applied to one sensor."""

    kind: FaultKind
    duration: FaultDuration
    sensor: str
    onset_before_failure: int | None = Field(
        default=None,
        description="Cycles before failure at which the fault begins. None means "
        "the onset was drawn at random from a recorded seed.",
    )
    severity_sd: float | None = Field(
        default=None, description="Drift magnitude in training standard deviations."
    )
    sign: int | None = None
    ramp_cycles: int | None = None
    length: int | None = Field(default=None, description="Transient length in cycles.")
    seed: int | None = None

    @property
    def scenario_id(self) -> str:
        parts = [self.kind.value, self.duration.value, self.sensor]
        if self.onset_before_failure is not None:
            parts.append(f"on{self.onset_before_failure}")
        else:
            parts.append("onrand")
        if self.severity_sd is not None:
            parts.append(f"sd{self.severity_sd:g}")
        if self.sign is not None:
            parts.append("pos" if self.sign > 0 else "neg")
        if self.length is not None:
            parts.append(f"len{self.length}")
        return "-".join(parts)

    def label(self) -> str:
        """Human-readable description for the UI and reports."""
        base = {
            FaultKind.dropout: "Dropout",
            FaultKind.stuck: "Stuck reading",
            FaultKind.drift: "Drift",
        }[self.kind]
        bits = [f"{base} on {self.sensor}"]
        if self.kind == FaultKind.drift and self.severity_sd is not None:
            direction = "up" if (self.sign or 1) > 0 else "down"
            bits.append(f"{self.severity_sd:g} SD {direction}")
        if self.duration == FaultDuration.transient and self.length:
            bits.append(f"{self.length}-cycle")
        else:
            bits.append("persistent")
        if self.onset_before_failure is not None:
            bits.append(f"from {self.onset_before_failure} cycles out")
        else:
            bits.append("random onset")
        return ", ".join(bits)


CLEAN_SCENARIO_ID = "clean"


# ---------------------------------------------------------------------------
# Alerts and measures
# ---------------------------------------------------------------------------


class WilsonInterval(Strict):
    lower: float
    upper: float
    level: float = 0.95


class AlertEpisode(Strict):
    start_cycle: int
    end_cycle: int
    start_rul: int
    end_rul: int
    still_open_at_failure: bool = False
    peak_score: float | None = Field(
        default=None, description="Highest score reached while the alert was active."
    )

    @property
    def length(self) -> int:
        return self.end_cycle - self.start_cycle + 1


class EngineOutcome(Strict):
    """Per-engine result, which keeps the engine counts auditable."""

    equipment_id: str
    detected: bool
    late: bool
    missed: bool
    lead_time: int | None = None
    episode_count: int = 0


class AlertMetrics(Strict):
    """Operational measures as defined in the proposal.

    ``detection_fraction`` counts engines, never cycles, and repeated fault runs
    on the same engine do not inflate the denominator.
    """

    engines: int
    detected: int
    late: int
    missed: int
    detection_fraction: float
    detection_ci: WilsonInterval
    early_alarm_burden: float = Field(
        description="Fraction of eligible cycles (rul > transition band) spent in alarm."
    )
    new_episodes_per_1000: float
    median_lead_time: float | None
    eligible_cycles: int
    scored_cycles: int

    @property
    def detection_percent(self) -> float:
        return 100.0 * self.detection_fraction


class ScenarioResult(Strict):
    """One candidate, at one threshold, under one scenario, on one partition."""

    scenario_id: str
    candidate: CandidateKind
    config_id: str
    partition: Partition
    threshold: float
    fault: FaultSpec | None = None
    metrics: AlertMetrics
    required: bool = Field(
        default=False, description="Part of the bounded set used for selection."
    )
    run_id: str | None = None


# ---------------------------------------------------------------------------
# Calibration and explanation
# ---------------------------------------------------------------------------


class ReliabilityBin(Strict):
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


class CalibrationReport(Strict):
    candidate: CandidateKind
    config_id: str
    partition: Partition
    brier: float
    bins: list[ReliabilityBin]
    note: str = (
        "Scores are compared against observed labels. Poorly calibrated scores "
        "are reported as such rather than presented as probabilities."
    )


class ShapContribution(Strict):
    feature: str
    value: float | None
    contribution: float


class AlertExplanation(Strict):
    equipment_id: str
    cycle: int
    score: float
    base_value: float | None = None
    contributions: list[ShapContribution] = Field(default_factory=list)
    available: bool = True
    note: str = (
        "Attributions describe model behaviour, not physical fault causes."
    )


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


class AcceptanceCriteria(Strict):
    """Set by the engineer before selection, recorded with the result."""

    min_detection_fraction: float
    max_early_alarm_burden: float
    min_useful_lead: int
    horizon_cycles: int


class CandidateVerdict(Strict):
    candidate: CandidateKind
    config_id: str
    threshold: float
    clean: AlertMetrics
    passes_clean: bool
    required_scenarios: int
    required_passed: int
    passes_all_required: bool
    mean_detection_required: float
    worst_detection_required: float
    worst_scenario_id: str | None = None
    worst_metrics: AlertMetrics | None = Field(
        default=None,
        description="Full measures for the worst required scenario. Carrying the "
        "interval as well as the point estimate keeps a small drop from being read "
        "as real when the sample cannot support the comparison.",
    )
    failing_scenarios: list[str] = Field(
        default_factory=list,
        description="Required scenarios that fell short of the criteria.",
    )
    qualifies: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def detection_drop(self) -> float:
        """Detection lost between clean data and the worst required fault."""
        return self.clean.detection_fraction - self.worst_detection_required


class SelectionResult(Strict):
    outcome: SelectionOutcome
    criteria: AcceptanceCriteria
    ranked: list[CandidateVerdict]
    recommended: CandidateVerdict | None = None
    partition: Partition = Partition.out_of_fold
    notes: list[str] = Field(default_factory=list)
    uncertain_comparisons: list[str] = Field(
        default_factory=list,
        description="Pairs whose detection intervals overlap, so the ordering is "
        "not established by the data.",
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class ReplayPoint(Strict):
    cycle: int
    rul: int
    score: float
    alert: bool
    sensor_clean: float | None = None
    sensor_faulted: float | None = None


class ReplaySeries(Strict):
    equipment_id: str
    candidate: CandidateKind
    config_id: str
    scenario_id: str
    threshold: float
    fault: FaultSpec | None = None
    fault_onset_rul: int | None = Field(
        default=None,
        description="Cycles before failure at which the fault actually began on this "
        "history. A random-onset scenario resolves to a different cycle per engine.",
    )
    fault_affected_cycles: int = 0
    points: list[ReplayPoint]
    episodes: list[AlertEpisode]
    outcome: EngineOutcome
    failure_cycle: int


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class RunRecord(Strict):
    """An entry in the evidence store.

    Every number shown in the application resolves to one of these, which is
    what makes the report's claim of traceability checkable.
    """

    run_id: str
    kind: Literal["profile", "training", "fault_matrix", "selection", "final_evaluation", "export"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config_fingerprint: str
    data_hash: str | None = None
    seed: int | None = None
    git_commit: str | None = None
    parent_run_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ReproducibilityCheck(Strict):
    run_id: str
    repeat_run_id: str
    tolerance: float
    max_absolute_difference: float
    metrics_compared: int
    reproduced: bool


class EvidenceBundle(Strict):
    """What the hosted replay service serves. Committed to the repository."""

    schema_version: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    config: dict[str, Any]
    config_fingerprint: str
    git_commit: str | None = None
    profile: DatasetProfile
    splits: SplitAssignment
    candidates: list[CandidateConfig]
    development_selection: SelectionResult
    final_evaluation: SelectionResult | None = None
    scenario_results: list[ScenarioResult]
    calibration: list[CalibrationReport] = Field(default_factory=list)
    replay_series: list[ReplaySeries] = Field(default_factory=list)
    explanations: list[AlertExplanation] = Field(default_factory=list)
    runs: list[RunRecord] = Field(default_factory=list)
    reproducibility: ReproducibilityCheck | None = None
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Copilot
# ---------------------------------------------------------------------------


class ToolInvocation(Strict):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    duration_ms: float | None = None
    run_ids: list[str] = Field(default_factory=list)


class NumericClaim(Strict):
    text: str
    value: float
    verified: bool
    matched_metric: str | None = None


class CopilotAnswer(Strict):
    text: str
    tool_calls: list[ToolInvocation] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    claims: list[NumericClaim] = Field(default_factory=list)
    unverified_claims: int = 0
    truncated: bool = Field(
        default=False, description="The tool-call budget was exhausted."
    )
    degraded: bool = Field(
        default=False, description="No LLM was available; a deterministic answer was returned."
    )


class CopilotRequest(Strict):
    question: str = Field(min_length=1, max_length=2000)
    candidate: CandidateKind | None = None
    scenario_id: str | None = None
