"""Public contract for contextual analysis. Numeric content is resolved by the server."""

from typing import Literal

from pydantic import Field, model_validator

from app.schemas import ColumnMapping, Partition, Strict


class AnalysisRequest(Strict):
    task: Literal["investigate", "compare", "warning", "brief", "data"]
    experiment_id: str | None = None
    dataset_id: str | None = None
    mapping: ColumnMapping | None = None
    complete_histories: bool = False
    partition: Partition = Partition.out_of_fold
    candidates: list[str] = Field(default_factory=list, max_length=2)
    scenario_id: str | None = Field(default=None, max_length=240)
    equipment_id: str | None = Field(default=None, max_length=200)
    cycle: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def exact_context(self):
        if self.task == "data":
            if not self.dataset_id or self.experiment_id or self.candidates or self.partition != Partition.out_of_fold or self.scenario_id or self.equipment_id or self.cycle is not None:
                raise ValueError("Choose one dataset for data review.")
            return self
        if self.dataset_id or self.mapping or self.complete_histories:
            raise ValueError("Dataset fields are only available for data review.")
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError("Choose different model configurations.")
        if self.task == "compare" and len(self.candidates) != 2:
            raise ValueError("Choose exactly two models to compare.")
        if self.task == "brief" and len(self.candidates) not in (1, 2):
            raise ValueError("Choose one or two models for a review brief.")
        if self.task not in ("compare", "brief") and len(self.candidates) != 1:
            raise ValueError("Choose one model for this analysis.")
        if self.task == "warning" and (not self.scenario_id or not self.equipment_id):
            raise ValueError("Choose a recorded history and scenario.")
        return self

    @property
    def consent_scope(self):
        return f"dataset:{self.dataset_id}" if self.task == "data" else self.experiment_id


class AnalysisClaim(Strict):
    id: str
    text: str
    source_ids: list[str]


class InvestigationCall(Strict):
    name: str
    label: str
    source_ids: list[str] = Field(default_factory=list)


class EvidenceReference(Strict):
    id: str
    label: str
    candidate: str
    partition: Partition
    scenario_id: str | None = None
    equipment_id: str | None = None
    cycle: int | None = None
    metric: str
    value: str
    unit: str
    display: str = Field(description="Server-formatted value shown to people; never supplied by the provider.")
    context: str = Field(description="Model, scenario and evaluation context for this reference.")
    href: str


class AnalysisFinding(Strict):
    id: str
    title: str
    detail: str
    tone: Literal["neutral", "success", "warning", "danger"] = "neutral"
    source_ids: list[str]


class AnalysisAction(Strict):
    id: str
    label: str
    detail: str
    href: str


class AnalysisResult(Strict):
    title: str
    summary: str
    findings: list[AnalysisFinding]
    sources: list[EvidenceReference]
    actions: list[AnalysisAction]
    limitations: list[str]
    evidence_digest: str
    interpretation: str | None = Field(default=None, description="Generated interpretation without numbers, links or verdicts.")
    brief_draft: str | None = None
    mode: Literal["evidence", "ai"] = "evidence"
    model: str | None = None
    prompt_version: str = "sidekick-analysis-v2.2"
    verification: str = "Evidence references checked"
    fallback_reason: str | None = None
    assessment: list[AnalysisClaim] = Field(default_factory=list)
    investigation: list[InvestigationCall] = Field(default_factory=list)
    suggested_mapping: ColumnMapping | None = None


class AnalysisStage(Strict):
    id: str
    label: str
    status: Literal["pending", "running", "completed", "failed"]


class AnalysisRecord(Strict):
    id: str
    context: AnalysisRequest
    status: Literal["queued", "running", "completed", "cancelled", "interrupted", "failed"]
    created_at: float
    updated_at: float
    stages: list[AnalysisStage]
    result: AnalysisResult | None = None
    error: str | None = None
    brief_text: str | None = None
    brief_saved_at: float | None = None
    cache_fingerprint: str | None = None
    reused: bool = False


class AssistantCapabilities(Strict):
    tasks: list[str]
    live_available: bool
    unlock_available: bool
    unlocked: bool
    consent_required: bool
    consent_granted: bool
    mode: Literal["full", "demo", "replay"]
    note: str


class ConsentUpdate(Strict):
    allowed: bool


class ConsentState(Strict):
    experiment_id: str
    allowed: bool
    disclosure: str


class AssistantAccess(Strict):
    code: str = Field(min_length=1, max_length=200)


class BriefUpdate(Strict):
    text: str = Field(max_length=12000)
    draft_only: bool = False
