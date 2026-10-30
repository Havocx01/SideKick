"""Scenario proposals and local policy checks."""
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator

from app.faults.scenarios import FaultCase
from app.investigator.records import Frozen, InvestigationRecord

if TYPE_CHECKING:
    from app.faults.evaluator import FixedDevelopmentEvaluator

MAX_PROPOSAL_BYTES = 16 * 1024


class Hypothesis(Frozen):
    suspected: str = Field(min_length=1, max_length=400)
    supportIf: str = Field(min_length=1, max_length=400)
    weakenIf: str = Field(min_length=1, max_length=400)
    basedOn: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("suspected", "supportIf", "weakenIf")
    @classmethod
    def validateText(cls, value):
        if not value.strip():
            raise ValueError("Hypothesis fields cannot be blank")
        return value.strip()


class ScenarioProposal(Frozen):
    scenario: FaultCase
    reason: str = Field(min_length=1, max_length=1600)
    hypothesis: Hypothesis | None = None

    @field_validator("reason")
    @classmethod
    def validateReason(cls, value):
        if not value.strip():
            raise ValueError("Explain why this scenario should be tested")
        return value.strip()


class ExplicitOnset(Frozen):
    mode: Literal["explicit"]
    onset_before_failure: int = Field(ge=1, le=100000)


class SeededOnset(Frozen):
    mode: Literal["seeded"]
    seed: int = Field(ge=0, le=2**32 - 1)


class Persistent(Frozen):
    mode: Literal["persistent"]


class Transient(Frozen):
    mode: Literal["transient"]
    length: int = Field(ge=1, le=100000)


class DriftFault(Frozen):
    kind: Literal["drift"]
    sensor: str = Field(min_length=1, max_length=128)
    onset: ExplicitOnset | SeededOnset
    duration: Persistent | Transient
    severity_sd: float = Field(gt=0, le=100)
    sign: Literal[-1, 1]
    ramp_cycles: int = Field(ge=1, le=100000)


class LossFault(Frozen):
    kind: Literal["dropout", "stuck"]
    sensor: str = Field(min_length=1, max_length=128)
    onset: ExplicitOnset | SeededOnset
    duration: Persistent | Transient


class ProviderScenario(Frozen):
    components: list[DriftFault | LossFault] = Field(min_length=1, max_length=4)


class ProviderProposal(Frozen):
    """Provider-facing shape: each alternative only has fields that apply to it."""
    scenario: ProviderScenario
    reason: str = Field(min_length=1, max_length=1600)
    hypothesis: Hypothesis | None

    def toProposal(self) -> ScenarioProposal:
        components = []
        for item in self.scenario.components:
            component = {"sensor": item.sensor, "kind": item.kind, "duration": item.duration.mode}
            if item.onset.mode == "explicit":
                component["onset_before_failure"] = item.onset.onset_before_failure
            else:
                component["seed"] = item.onset.seed
            if item.duration.mode == "transient":
                component["length"] = item.duration.length
            if item.kind == "drift":
                component.update(severity_sd=item.severity_sd, sign=item.sign, ramp_cycles=item.ramp_cycles)
            components.append(component)
        return ScenarioProposal.model_validate({"scenario": {"components": components}, "reason": self.reason,
            "hypothesis": self.hypothesis.model_dump() if self.hypothesis else None})


def validateProposal(payload: str, record: InvestigationRecord, evaluator: "FixedDevelopmentEvaluator") -> ScenarioProposal:
    if not isinstance(payload, str):
        raise ValueError("Proposal must be JSON text")
    if len(payload.encode("utf-8")) > MAX_PROPOSAL_BYTES:
        raise ValueError("Proposal exceeds its size limit")
    record = InvestigationRecord.model_validate_json(record.model_dump_json(), strict=True)
    record.check_context(evaluator)
    proposal = ScenarioProposal.model_validate_json(payload, strict=True)
    record.policy.check(proposal.scenario, evaluator.config)
    return proposal
