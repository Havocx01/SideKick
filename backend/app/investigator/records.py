"""Local investigation records."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
from typing import Literal, TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.faults.scenarios import FaultPolicy
from app.schemas import Strict

if TYPE_CHECKING:
    from app.faults.evaluator import FixedDevelopmentEvaluator

MAX_RECORD_BYTES = 128 * 1024


class Frozen(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class InvestigationBudget(Frozen):
    max_experiments: int = Field(ge=1, le=128, strict=True)
    max_proposals: int = Field(ge=1, le=256, strict=True)
    max_seconds: float = Field(gt=0, le=3600, strict=True)


class FixedThreshold(Frozen):
    candidate: str = Field(min_length=1, max_length=256)
    threshold: float = Field(strict=True)


class CreatedEvent(Frozen):
    kind: Literal["created"] = "created"
    occurred_at: float = Field(ge=0, strict=True)


class InvestigationRecord(Frozen):
    version: Literal[1] = 1
    id: str
    created_at: float = Field(ge=0, strict=True)
    status: Literal["ready"] = "ready"
    partition: Literal["out_of_fold"] = "out_of_fold"
    objective: str = Field(min_length=1, max_length=2000)
    context_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_fingerprint: str = Field(pattern=r"^[a-f0-9]{16}$")
    policy: FaultPolicy
    thresholds: tuple[FixedThreshold, ...] = Field(min_length=1, max_length=10)
    budget: InvestigationBudget
    history: tuple[CreatedEvent, ...] = Field(min_length=1, max_length=1)

    @field_validator("id")
    @classmethod
    def validateId(cls, value):
        return str(UUID(value))

    @field_validator("objective")
    @classmethod
    def validateObjective(cls, value):
        if not value.strip():
            raise ValueError("Describe an investigation objective")
        return value.strip()

    @model_validator(mode="after")
    def validateSetup(self):
        if self.budget.max_experiments > self.policy.max_evaluations:
            raise ValueError("Investigation budget exceeds the fixed evaluation policy")
        names = [item.candidate for item in self.thresholds]
        if len(set(names)) != len(names) or names != sorted(names):
            raise ValueError("Fixed model thresholds must be unique and sorted")
        if self.history[0].occurred_at != self.created_at:
            raise ValueError("Creation history must match the record timestamp")
        return self

    def check_context(self, evaluator: "FixedDevelopmentEvaluator") -> None:
        if (self.context_fingerprint != evaluator.context_fingerprint
                or self.config_fingerprint != evaluator.config.fingerprint()
                or self.policy != evaluator.policy
                or {item.candidate: item.threshold for item in self.thresholds} != evaluator.thresholds):
            raise ValueError("Investigation does not match the fixed evaluation context")


class InvestigationCapacityError(RuntimeError):
    pass


class InvestigationStore:
    def __init__(self, root: Path, *, max_records: int = 1000):
        if type(max_records) is not int or not 1 <= max_records <= 10000:
            raise ValueError("Choose a record capacity between 1 and 10000")
        self.max_records = max_records
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "investigator.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS investigations (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, evaluator: "FixedDevelopmentEvaluator", *, objective: str, budget: InvestigationBudget) -> InvestigationRecord:
        now = time.time()
        # Revalidate nested values because model_copy can bypass Pydantic validation.
        record = InvestigationRecord.model_validate({
            "id": str(uuid4()), "created_at": now, "objective": objective,
            "context_fingerprint": evaluator.context_fingerprint,
            "config_fingerprint": evaluator.config.fingerprint(),
            "policy": evaluator.policy.model_dump(mode="json"),
            "thresholds": [{"candidate": name, "threshold": threshold} for name, threshold in sorted(evaluator.thresholds.items())],
            "budget": budget.model_dump(mode="json"),
            "history": [{"kind": "created", "occurred_at": now}],
        })
        payload = record.model_dump_json()
        if len(payload.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("Investigation metadata exceeds its storage limit")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM investigations").fetchone()[0] >= self.max_records:
                raise InvestigationCapacityError("Investigation record capacity reached")
            db.execute("INSERT INTO investigations (id,payload) VALUES (?,?)", (record.id, payload))
        return record

    def get(self, id: str) -> InvestigationRecord:
        id = str(UUID(id))
        with self.connect() as db:
            # Bound reads even when the database was edited outside this store.
            row = db.execute("SELECT CASE WHEN length(CAST(payload AS BLOB)) <= ? THEN payload END "
                "FROM investigations WHERE id=?", (MAX_RECORD_BYTES, id)).fetchone()
        if row is None:
            raise KeyError(id)
        if row[0] is None:
            raise ValueError("Investigation metadata exceeds its storage limit")
        record = InvestigationRecord.model_validate_json(row[0])
        if record.id != id:
            raise ValueError("Stored investigation identity does not match its row")
        return record
