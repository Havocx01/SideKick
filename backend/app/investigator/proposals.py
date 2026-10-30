"""Scenario proposals and local policy checks."""
from typing import TYPE_CHECKING

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
