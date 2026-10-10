"""The contract shared by the pipeline, the API and the frontend."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from uuid import UUID


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)


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


class ColumnMapping(Strict):
    equipment_id: str
    cycle_index: str
    sensors: list[str]
    failure_cycle: str | None = None
    ignored: list[str] = Field(default_factory=list)
    inferred: bool = False
    ambiguous: list[str] = Field(
        default_factory=list,
        description="Columns the profiler could not assign confidently. The engineer confirms these before training.",
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


class SplitAssignment(Strict):
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


class FaultSpec(Strict):
    kind: FaultKind
    duration: FaultDuration
    sensor: str
    onset_before_failure: int | None = Field(
        default=None,
        description="Cycles before failure at which the fault begins. None means "
        "the onset was drawn at random from a recorded seed.",
    )
    severity_sd: float | None = Field(default=None, description="Drift magnitude in training standard deviations.")
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
        if self.ramp_cycles not in (None, 20):
            parts.append(f"ramp{self.ramp_cycles}")
        if self.seed is not None:
            parts.append(f"seed{self.seed}")
        return "-".join(parts)

    def label(self) -> str:
        base = {FaultKind.dropout: "Dropout", FaultKind.stuck: "Stuck reading", FaultKind.drift: "Drift"}[self.kind]
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


class FaultScenario(Strict):
    fault: FaultSpec
    required: bool = True


class ExperimentProtocol(Strict):
    version: int = 1
    min_useful_lead: int = Field(default=10, ge=1)
    horizon_cycles: int = Field(default=30, ge=2)
    transition_band_end: int = Field(default=45, ge=3)
    min_detection_fraction: float = Field(default=0.70, ge=0, le=1, allow_inf_nan=False)
    max_early_alarm_burden: float = Field(default=0.10, ge=0, le=1, allow_inf_nan=False)
    scenarios: list[FaultScenario] = Field(default_factory=list, max_length=128)
    base_seed: int = Field(default=20260918, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def validate_protocol(self):
        if not self.min_useful_lead < self.horizon_cycles < self.transition_band_end:
            raise ValueError("Use minimum lead < warning horizon < early-alarm boundary.")
        if self.scenarios and not any(s.required for s in self.scenarios):
            raise ValueError("Mark at least one sensor fault as required.")
        ids = [s.fault.scenario_id for s in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("Remove duplicate fault scenarios.")
        for entry in self.scenarios:
            spec = entry.fault
            if spec.onset_before_failure is None or spec.onset_before_failure < self.min_useful_lead:
                raise ValueError("Fault onset must be an integer at or before the minimum useful lead.")
            if spec.duration == FaultDuration.transient and (spec.length is None or spec.length < 1):
                raise ValueError("Transient faults need a positive length in cycles.")
            if spec.kind == FaultKind.drift:
                if spec.severity_sd is None or not 0 < spec.severity_sd <= 100 or spec.sign not in (-1, 1):
                    raise ValueError("Drift needs a finite positive severity and a direction.")
                if spec.ramp_cycles is None or spec.ramp_cycles < 1:
                    raise ValueError("Drift needs a positive ramp length.")
        return self


class PilotBrief(Strict):
    equipment_family: str = Field(default="", max_length=200)
    reviewing_engineer: str = Field(default="", max_length=200)
    current_procedure: str = Field(default="", max_length=2000)
    intended_decision: str = Field(default="", max_length=2000)
    success_measure: str = Field(default="", max_length=1000)
    data_classification: Literal["simulated", "field", "unverified"] = "unverified"


class PilotAgreementCreate(Strict):
    brief: PilotBrief
    single_family_confirmed: bool
    failure_labels_checked: bool
    representative_data_confirmed: bool
    protocol_agreed: bool

    @model_validator(mode="after")
    def checked_brief(self):
        for field in ("equipment_family", "reviewing_engineer", "current_procedure", "intended_decision", "success_measure"):
            if not getattr(self.brief, field).strip():
                raise ValueError("Complete the equipment, reviewer, decision and success measure before agreeing the pilot.")
        if self.brief.data_classification == "unverified":
            raise ValueError("Identify the data as field records or simulated data.")
        if not all((self.single_family_confirmed, self.failure_labels_checked,
                    self.representative_data_confirmed, self.protocol_agreed)):
            raise ValueError("Check the data and agree the warning window, fault cases and limits first.")
        return self


class PilotAgreementRecord(PilotAgreementCreate):
    agreement_id: str
    experiment_id: str
    dataset_id: str
    data_source: Literal["synthetic", "upload"]
    data_hash: str
    config_fingerprint: str
    source_digest: str
    candidate: str
    created_at: float


class PilotDecision(str, Enum):
    supervised_trial = "supervised_trial"
    revise_model = "revise_model"
    collect_data = "collect_data"
    stop = "stop"


class PilotOutcomeCreate(Strict):
    reviewing_engineer: str = Field(min_length=1, max_length=200)
    decision: PilotDecision
    decision_changed: bool
    observations: str = Field(min_length=1, max_length=2000)
    baseline_review_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    sidekick_review_minutes: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    evidence_reviewed: bool

    @model_validator(mode="after")
    def checked_review(self):
        if not self.reviewing_engineer.strip() or not self.observations.strip() or not self.evidence_reviewed:
            raise ValueError("Name the reviewer, record the reason and confirm the evidence was reviewed.")
        if (self.baseline_review_minutes is None) != (self.sidekick_review_minutes is None):
            raise ValueError("Provide both review times or leave both blank.")
        return self


class PilotOutcomeRecord(PilotOutcomeCreate):
    review_id: str
    agreement_id: str
    experiment_id: str
    validation_id: str
    freeze_id: str
    artifact_digest: str
    final_qualifies: bool
    review_minutes_saved: float | None = None
    created_at: float


class PilotReviewRecord(Strict):
    agreement: PilotAgreementRecord
    outcome: PilotOutcomeRecord | None = None


class PilotState(Strict):
    record: PilotReviewRecord | None = None
    agreement: PilotAgreementRecord | None = None
    outcome: PilotOutcomeRecord | None = None
    phase: Literal["agreement", "evaluation", "review", "complete"]
    agreement_blocked: str | None = None
    review_blocked: str | None = None
    final_qualifies: bool | None = None


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
    peak_score: float | None = Field(default=None, description="Highest score reached while the alert was active.")

    @property
    def length(self) -> int:
        return self.end_cycle - self.start_cycle + 1


class EngineOutcome(Strict):
    equipment_id: str
    detected: bool
    late: bool
    missed: bool
    lead_time: int | None = None
    episode_count: int = 0


class AlertMetrics(Strict):
    """Detection counts equipment; repeated faults do not increase the sample size."""

    engines: int
    detected: int
    late: int
    missed: int
    detection_fraction: float
    detection_ci: WilsonInterval
    early_alarm_burden: float | None = Field(description="Fraction of eligible cycles spent in alarm; unavailable with no eligible cycles.")
    new_episodes_per_1000: float
    median_lead_time: float | None
    eligible_cycles: int
    scored_cycles: int

    @property
    def detection_percent(self) -> float:
        return 100.0 * self.detection_fraction


class ScenarioResult(Strict):
    scenario_id: str
    candidate: CandidateKind
    config_id: str
    partition: Partition
    threshold: float
    fault: FaultSpec | None = None
    metrics: AlertMetrics
    required: bool = Field(default=False, description="Part of the bounded set used for selection.")
    run_id: str | None = None
    expected_engines: int | None = None
    coverage_complete: bool | None = None
    coverage_notes: list[str] = Field(default_factory=list)


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
    note: str = "Attributions describe model behaviour, not physical fault causes."
    candidate: str | None = None
    partition: Partition = Partition.out_of_fold


class AcceptanceCriteria(Strict):
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
        default_factory=list, description="Required scenarios that fell short of the criteria."
    )
    qualifies: bool = False
    notes: list[str] = Field(default_factory=list)
    worst_burden_required: float | None = None
    worst_burden_scenario_id: str | None = None
    coverage_complete: bool | None = None

    @property
    def detection_drop(self) -> float:
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
        description="Pairs whose detection intervals overlap, so the ordering is not established by the data.",
    )


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
    partition: Partition = Partition.out_of_fold
    representative_reason: str | None = None


class PairedComparison(Strict):
    first: str
    second: str
    kind: Literal["selected", "matched_augmentation"]
    engines: int
    scenarios: int
    resamples: int = 1000
    seed: int
    detection_delta: float
    detection_interval: list[float]
    burden_delta: float | None = None
    burden_interval: list[float] | None = None
    note: str = "Exploratory development comparison, conditional on selected thresholds and configurations."


class FrozenModelRecord(Strict):
    freeze_id: str
    experiment_id: str
    job_id: str
    candidate: str
    status: str = "queued"
    manifest: dict[str, Any] = Field(default_factory=dict)
    artifact_digest: str | None = None
    manifest_digest: str | None = None
    created_at: float
    error: str | None = None


class ValidationRecord(Strict):
    validation_id: str
    experiment_id: str
    freeze_id: str
    job_id: str
    status: str = "queued"
    untouched_confirmed: bool
    exposure_started_at: float | None = None
    created_at: float
    error: str | None = None


class ExposureRecord(Strict):
    history_id: str
    experiment_id: str
    reason: str
    exposed_at: float


class RunRecord(Strict):
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
    schema_version: int = 1
    experiment_id: str | None = None
    dataset_id: str | None = None
    source_digest: str | None = None
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    confirmed_mapping: ColumnMapping | None = None
    complete_histories_confirmed: bool | None = None
    holdout_status: str = "Historical benchmark: previously examined holdout engines are exposed."
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
    protocol: ExperimentProtocol | None = None
    pilot_brief: PilotBrief | None = None
    paired_comparisons: list[PairedComparison] = Field(default_factory=list)
    frozen_model: FrozenModelRecord | None = None
    validation: ValidationRecord | None = None
    pilot_review: PilotReviewRecord | None = None


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    cancelling = "cancelling"
    completed = "completed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    interrupted = "interrupted"
    failed = "failed"


class DatasetConfirmation(Strict):
    mapping: ColumnMapping
    complete_histories: bool = False


class DatasetRegistration(Strict):
    dataset_id: str
    name: str
    source: Literal["synthetic", "upload"]
    columns: list[str]
    preview: list[dict[str, Any]]
    row_count: int
    mapping: ColumnMapping | None = None
    complete_histories: bool = False
    confirmed: bool = False
    profile: DatasetProfile | None = None
    splits: SplitAssignment | None = None


class ExperimentCreate(Strict):
    dataset_id: str
    folder_id: UUID | None = None
    min_detection_fraction: float = Field(default=0.70, ge=0, le=1)
    max_early_alarm_burden: float = Field(default=0.10, ge=0, le=1)
    protocol: ExperimentProtocol | None = None
    pilot_brief: PilotBrief | None = None


class ValidationCreate(Strict):
    untouched_confirmed: bool


class ExperimentRecord(Strict):
    experiment_id: str
    dataset_id: str
    name: str
    source: Literal["synthetic", "upload"]
    status: JobStatus
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    elapsed_seconds: float = 0
    stage: str = "queued"
    completed_work: int = 0
    total_work: int | None = None
    work_unit: str = ""
    error: str | None = None
    config: dict[str, Any]
    config_fingerprint: str
    data_hash: str
    source_digest: str
    job_kind: Literal["development", "freeze", "validation"] = "development"
    parent_experiment_id: str | None = None
    operation_id: str | None = None
    pilot_brief: PilotBrief | None = None


class ExperimentDetail(ExperimentRecord):
    """Read-only library label, absent from recorded job and evidence payloads."""

    display_name: str | None = Field(default=None, json_schema_extra={"readOnly": True})


class LibraryFolderInput(Strict):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class LibraryFolder(Strict):
    id: str
    name: str


class LibraryItemRef(Strict):
    kind: Literal["run", "upload"]
    id: UUID


class LibraryUpdate(Strict):
    items: list[LibraryItemRef] = Field(min_length=1, max_length=100)
    action: Literal["rename", "move", "archive", "restore"]
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    folder_id: UUID | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def valid_action(self):
        if self.action == "rename" and (len(self.items) != 1 or self.display_name is None):
            raise ValueError("Rename one item at a time and supply its new name.")
        if self.action != "rename" and self.display_name is not None:
            raise ValueError("A display name is only used when renaming an item.")
        if self.action != "move" and self.folder_id is not None:
            raise ValueError("A folder is only used when moving items.")
        return self


class LibraryItem(Strict):
    kind: Literal["run", "upload"]
    id: str
    dataset_id: str
    display_name: str
    original_name: str
    source: Literal["synthetic", "upload"]
    folder_id: str | None = None
    archived: bool = False
    created_at: float | None = None
    status: str
    run_count: int = 0
    row_count: int | None = None


class LibrarySnapshot(Strict):
    folders: list[LibraryFolder]
    items: list[LibraryItem]


class GuideAnswer(Strict):
    question: str
    answer: str
    link: str
    link_label: str


class DecisionReport(Strict):
    title: str
    qualification_reason: str
    summary: str
    fault_summary: str
    augmentation_summary: str
    unaugmented: CandidateVerdict | None = None
    augmented: CandidateVerdict | None = None
    limitations: list[str]
    guide: list[GuideAnswer]
    inspected_candidate: str | None = None
    partition: Partition = Partition.out_of_fold


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
    truncated: bool = Field(default=False, description="The tool-call budget was exhausted.")
    degraded: bool = Field(default=False, description="No LLM was available; a deterministic answer was returned.")


class CopilotRequest(Strict):
    question: str = Field(min_length=1, max_length=2000)
    candidate: CandidateKind | None = None
    scenario_id: str | None = None
