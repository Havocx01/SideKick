"""HTTP contract for saved investigations."""
from typing import Any, Literal

from pydantic import Field

from app.faults.investigation import InvestigationState
from app.investigator.findings import Finding, FindingCriterion
from app.schemas import Strict

RequestId = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


class CleanMetrics(Strict):
    detection: float
    alarmBurden: float | None
    medianLead: float | None
    histories: int


class ContextInfo(Strict):
    name: str
    contextFingerprint: str
    profile: str | None
    sensors: list[str]
    thresholds: dict[str, float]
    clean: dict[str, CleanMetrics]


class InvestigationCreate(Strict):
    context: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    objective: str = Field(default="Find sensor faults that cost useful warnings.", min_length=1, max_length=2000)
    maxExperiments: int = Field(default=16, ge=1, le=128)
    maxFailures: int = Field(default=3, ge=1, le=64)
    maxAttemptsPerScenario: int = Field(default=2, ge=1, le=5)
    maxRunSeconds: float = Field(default=600, gt=0, le=3600)
    criterion: FindingCriterion | None = None
    seed: int = Field(default=0, ge=0, le=12)
    proposals: list[dict[str, Any]] = Field(default_factory=list, max_length=64)


class StartRequest(Strict):
    requestId: str = RequestId
    mode: Literal["run", "agent"] = "run"
    allowProvider: bool = False
    maxProviderCalls: int = Field(default=4, ge=1, le=64)
    maxCompletionTokens: int = Field(default=32768, ge=1, le=1000000)


class ReduceRequest(Strict):
    requestId: str = RequestId
    attempt: str = Field(min_length=1, max_length=64)
    maxExperiments: int = Field(default=16, ge=1, le=128)


class RemedyRequest(Strict):
    requestId: str = RequestId
    kind: Literal["threshold", "augmented"]
    threshold: float | None = None
    approveTraining: bool = False


class InvestigationEvent(Strict):
    sequence: int
    kind: str
    detail: str | None
    at: float


class InvestigationSummary(Strict):
    id: str
    context: str
    objective: str
    createdAt: float
    active: str | None
    stopReason: str | None
    experimentsUsed: int
    maxExperiments: int
    discoveries: int


class InvestigationView(InvestigationSummary):
    state: InvestigationState
    criterion: FindingCriterion | None
    findings: list[Finding]
    discoveryFamilies: list[str]
    controller: dict[str, Any] | None
    events: list[InvestigationEvent]
    reductions: list[dict[str, Any]]
    remedies: list[dict[str, Any]]


class ReplayCheck(Strict):
    attempt: str
    scenarioId: str
    matches: bool
    evidenceDigest: str
