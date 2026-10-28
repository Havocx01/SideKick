"""Durable, bounded execution of saved fault-scenario proposals.

An investigation is bound to one fixed evaluator context (fitted models,
thresholds, data and policy). Proposals are untrusted JSON, typically written
by an agent; they are validated here and never trusted for budgets or identity.

Lifecycle of one experiment attempt:

    reserved -> running -> completed | failed | timed_out | cancelled | stopped
                       \\-> interrupted (runner died; recovered by the next run)

A slot is reserved in the same transaction that checks the budget, before any
work starts. A reservation that never started is released; every started
attempt consumes its slot. ``failed``, ``timed_out`` and ``interrupted`` are
failures; ``cancelled`` and ``stopped`` (the run's own time limit) are not the
scenario's fault and leave its proposal pending for a later run.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Literal
import uuid

from pydantic import Field, ValidationError, model_validator

from app.faults.evaluator import EvaluationStopped, FaultEvaluation, FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase, FaultPolicy
from app.schemas import Strict

MAX_PROPOSALS = 256
MAX_PROPOSAL_BYTES = 64 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024
LEASE_MARGIN_SECONDS = 60.0
HEARTBEAT_SECONDS = 1.0

SLOT_STATUSES = ("reserved", "running", "completed", "failed", "timed_out", "cancelled", "stopped", "interrupted")
FAILURE_STATUSES = ("failed", "timed_out", "interrupted")

ProposalStatus = Literal["pending", "rejected", "duplicate", "completed", "exhausted"]
AttemptStatus = Literal["reserved", "running", "completed", "failed", "timed_out", "cancelled", "stopped", "interrupted"]
StopReason = Literal["completed", "budget_exhausted", "failure_limit", "cancelled", "time_limit", "evaluator_budget"]


class InvestigationError(RuntimeError):
    pass


class InvestigationBusy(InvestigationError):
    """Another runner holds a live lease on this investigation."""


class LeaseLost(InvestigationError):
    """This runner's lease expired or was taken over; it must not write results."""


class InvestigationBudget(Strict):
    max_experiments: int = Field(default=16, ge=1, le=128, strict=True)
    max_failures: int = Field(default=3, ge=1, le=64, strict=True)
    max_attempts_per_scenario: int = Field(default=2, ge=1, le=5, strict=True)
    max_run_seconds: float = Field(default=600, gt=0, le=3600, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent(self):
        if self.max_failures > self.max_experiments:
            raise ValueError("The failure limit cannot exceed the experiment budget")
        return self


class ProposalState(Strict):
    id: str
    seq: int
    status: ProposalStatus
    scenario_id: str | None
    reason: str | None
    duplicate_of: str | None
    failed_attempts: int


class AttemptState(Strict):
    id: str
    proposal_id: str
    scenario_id: str
    status: AttemptStatus
    reason: str | None
    reserved_at: float
    started_at: float | None
    finished_at: float | None
    result_digest: str | None


class InvestigationState(Strict):
    id: str
    context_fingerprint: str
    policy_fingerprint: str
    budget: InvestigationBudget
    cancel_requested: bool
    stop_reason: StopReason | None
    slots_used: int
    failures: int
    proposals: list[ProposalState]
    attempts: list[AttemptState]


class RunSummary(Strict):
    investigation_id: str
    stop_reason: StopReason
    slots_used: int
    failures: int
    completed: list[str]
    failed: list[str]
    rejected: list[str]
    duplicates: list[str]
    interrupted_recovered: list[str]


def _short(error: BaseException) -> str:
    if isinstance(error, ValidationError):
        problems = error.errors(include_input=False, include_context=False, include_url=False)
        detail = "; ".join(f"{'.'.join(map(str, p['loc'])) or 'scenario'}: {p['msg']}" for p in problems[:3])
    else:
        detail = str(error)
    return f"{type(error).__name__}: {detail}"[:300]


class InvestigationStore:
    def __init__(self, root: Path):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "investigations.sqlite3"
        with self.transaction() as db:
            for statement in (
                "CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, context_fingerprint TEXT NOT NULL,"
                " policy TEXT NOT NULL, policy_fingerprint TEXT NOT NULL, budget TEXT NOT NULL, created REAL NOT NULL,"
                " cancel_requested INTEGER NOT NULL DEFAULT 0, stop_reason TEXT, lease_token TEXT, lease_expires REAL)",
                "CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES investigations(id),"
                " seq INTEGER NOT NULL, payload TEXT NOT NULL, scenario_id TEXT, status TEXT NOT NULL, reason TEXT,"
                " duplicate_of TEXT, UNIQUE(investigation, seq))",
                "CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES investigations(id),"
                " proposal TEXT NOT NULL REFERENCES proposals(id), scenario_id TEXT NOT NULL, status TEXT NOT NULL,"
                " lease_token TEXT NOT NULL, reason TEXT, reserved REAL NOT NULL, started REAL, finished REAL,"
                " result TEXT, result_digest TEXT)",
                "CREATE INDEX IF NOT EXISTS attempts_by_investigation ON attempts(investigation, status)",
            ):
                db.execute(statement)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")

    # ---- creation and proposals -------------------------------------------------

    def create(self, evaluator: FixedDevelopmentEvaluator, budget: InvestigationBudget | None = None, proposals=()) -> str:
        budget = InvestigationBudget.model_validate((budget or InvestigationBudget()).model_dump())
        if budget.max_experiments > evaluator.policy.max_evaluations:
            raise ValueError("The experiment budget exceeds the policy's evaluation limit")
        investigation = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO investigations(id,context_fingerprint,policy,policy_fingerprint,budget,created) VALUES(?,?,?,?,?,?)",
                (investigation, evaluator.context_fingerprint, json.dumps(evaluator.policy.model_dump(mode="json"), sort_keys=True),
                 evaluator.policy.fingerprint, budget.model_dump_json(), time.time()))
        if proposals:
            self.add_proposals(investigation, proposals)
        return investigation

    def add_proposals(self, investigation: str, proposals) -> list[str]:
        """Store untrusted proposals verbatim; validation happens when a run loads them."""
        payloads = []
        for proposal in proposals:
            text = proposal if isinstance(proposal, str) else json.dumps(proposal, sort_keys=True, allow_nan=False)
            if len(text.encode()) > MAX_PROPOSAL_BYTES:
                raise ValueError("Proposal exceeds its size limit")
            payloads.append(text)
        with self.transaction() as db:
            self._row(db, investigation)
            last, count = db.execute("SELECT COALESCE(MAX(seq),0), COUNT(*) FROM proposals WHERE investigation=?", (investigation,)).fetchone()
            if count + len(payloads) > MAX_PROPOSALS:
                raise ValueError("Investigation proposal limit reached")
            ids = []
            for offset, text in enumerate(payloads, start=1):
                ids.append(uuid.uuid4().hex)
                db.execute("INSERT INTO proposals(id,investigation,seq,payload,status) VALUES(?,?,?,?, 'pending')",
                    (ids[-1], investigation, last + offset, text))
            return ids

    # ---- cancellation ----------------------------------------------------------

    def request_cancel(self, investigation: str):
        """Safe from any process; an active run stops at its next cooperative check."""
        with self.transaction() as db:
            self._row(db, investigation)
            db.execute("UPDATE investigations SET cancel_requested=1 WHERE id=?", (investigation,))

    def resume(self, investigation: str):
        with self.transaction() as db:
            self._row(db, investigation)
            db.execute("UPDATE investigations SET cancel_requested=0, stop_reason=NULL WHERE id=?", (investigation,))

    def cancel_requested(self, investigation: str) -> bool:
        with self.connection() as db:
            return bool(self._row(db, investigation)["cancel_requested"])

    # ---- reading ---------------------------------------------------------------

    def load(self, investigation: str) -> InvestigationState:
        with self.connection() as db:
            row = self._row(db, investigation)
            failures = dict(db.execute(f"SELECT proposal, COUNT(*) FROM attempts WHERE investigation=? AND status IN ({_marks(FAILURE_STATUSES)})"
                " GROUP BY proposal", (investigation, *FAILURE_STATUSES)).fetchall())
            proposals = [ProposalState(id=id, seq=seq, status=status, scenario_id=scenario, reason=reason, duplicate_of=duplicate,
                    failed_attempts=failures.get(id, 0))
                for id, seq, status, scenario, reason, duplicate in db.execute(
                    "SELECT id,seq,status,scenario_id,reason,duplicate_of FROM proposals WHERE investigation=? ORDER BY seq", (investigation,))]
            attempts = [AttemptState(id=id, proposal_id=proposal, scenario_id=scenario, status=status, reason=reason,
                    reserved_at=reserved, started_at=started, finished_at=finished, result_digest=digest)
                for id, proposal, scenario, status, reason, reserved, started, finished, digest in db.execute(
                    "SELECT id,proposal,scenario_id,status,reason,reserved,started,finished,result_digest FROM attempts"
                    " WHERE investigation=? ORDER BY reserved, rowid", (investigation,))]
            slots, failed = self._usage(db, investigation)
        return InvestigationState(id=investigation, context_fingerprint=row["context_fingerprint"], policy_fingerprint=row["policy_fingerprint"],
            budget=InvestigationBudget.model_validate_json(row["budget"]), cancel_requested=bool(row["cancel_requested"]),
            stop_reason=row["stop_reason"], slots_used=slots, failures=failed, proposals=proposals, attempts=attempts)

    def result(self, attempt: str) -> FaultEvaluation:
        with self.connection() as db:
            found = db.execute("SELECT a.status, a.result, a.result_digest, a.scenario_id, i.context_fingerprint, i.policy_fingerprint"
                " FROM attempts a JOIN investigations i ON i.id=a.investigation WHERE a.id=?", (attempt,)).fetchone()
        if found is None:
            raise KeyError("Unknown experiment attempt")
        status, payload, digest, scenario, context, policy = found
        if status != "completed" or payload is None:
            raise ValueError("Experiment attempt has no recorded result")
        if hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise ValueError("Recorded result does not match its checksum")
        result = FaultEvaluation.model_validate_json(payload)
        if result.scenario_id != scenario or result.context_fingerprint != context or result.policy_fingerprint != policy:
            raise ValueError("Recorded result does not belong to this investigation")
        return result

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def _row(db, investigation):
        db.row_factory = sqlite3.Row
        try:
            row = db.execute("SELECT * FROM investigations WHERE id=?", (investigation,)).fetchone()
        finally:
            db.row_factory = None
        if row is None:
            raise KeyError("Unknown investigation")
        return row

    @staticmethod
    def _usage(db, investigation):
        slots = db.execute(f"SELECT COUNT(*) FROM attempts WHERE investigation=? AND status IN ({_marks(SLOT_STATUSES)})",
            (investigation, *SLOT_STATUSES)).fetchone()[0]
        failures = db.execute(f"SELECT COUNT(*) FROM attempts WHERE investigation=? AND status IN ({_marks(FAILURE_STATUSES)})",
            (investigation, *FAILURE_STATUSES)).fetchone()[0]
        return slots, failures


def _marks(values) -> str:
    return ",".join("?" for _ in values)


class ExperimentRunner:
    """Run one saved investigation against its fixed evaluator. One live runner per investigation."""

    def __init__(self, store: InvestigationStore, evaluator: FixedDevelopmentEvaluator, *, wall=time.time, monotonic=time.monotonic):
        self.store = store
        self.evaluator = evaluator
        self._wall = wall
        self._monotonic = monotonic

    def run(self, investigation: str, *, cancelled=None) -> RunSummary:
        token = uuid.uuid4().hex
        budget, recovered = self._acquire(investigation, token)
        deadline = self._monotonic() + budget.max_run_seconds
        summary = {"completed": [], "failed": [], "rejected": [], "duplicates": [], "interrupted_recovered": recovered}
        flags = {"lost": False, "cancel": False, "next_heartbeat": 0.0}

        def cancel_now() -> bool:
            if cancelled is not None and cancelled():
                flags["cancel"] = True
            now = self._monotonic()
            if not flags["cancel"] and now >= flags["next_heartbeat"]:
                flags["next_heartbeat"] = now + HEARTBEAT_SECONDS
                try:
                    flags["cancel"] = self._heartbeat(investigation, token)
                except LeaseLost:
                    flags["lost"] = True
            return flags["cancel"] or flags["lost"]

        def should_stop() -> bool:
            return cancel_now() or self._monotonic() >= deadline

        try:
            rejected, duplicates = self._validate(investigation, token)
            summary["rejected"], summary["duplicates"] = rejected, duplicates
            while True:
                if cancel_now():
                    if flags["lost"]:
                        raise LeaseLost("Investigation lease was lost")
                    reason = "cancelled"
                    break
                if self._monotonic() >= deadline:
                    reason = "time_limit"
                    break
                admission = self._reserve(investigation, token, budget)
                if isinstance(admission, str):
                    reason = admission
                    break
                attempt, proposal, payload, scenario_id = admission
                if cancel_now():  # Pre-start cancellation releases the reservation.
                    self._release(investigation, token, attempt)
                    if flags["lost"]:
                        raise LeaseLost("Investigation lease was lost")
                    reason = "cancelled"
                    break
                self._start(investigation, token, attempt)
                outcome = self._execute(investigation, token, attempt, proposal, payload, scenario_id, budget, should_stop, flags, deadline)
                if outcome == "completed":
                    summary["completed"].append(attempt)
                elif outcome in FAILURE_STATUSES:
                    summary["failed"].append(attempt)
                elif outcome == "cancelled":
                    reason = "cancelled"
                    break
                elif outcome == "stopped":
                    reason = "time_limit"
                    break
            self._finish(investigation, token, reason)
        finally:
            self._unlock(investigation, token)
        state = self.store.load(investigation)
        return RunSummary(investigation_id=investigation, stop_reason=reason, slots_used=state.slots_used,
            failures=state.failures, **summary)

    # ---- lease -----------------------------------------------------------------

    def _ttl(self) -> float:
        return float(self.evaluator.policy.max_seconds) + LEASE_MARGIN_SECONDS

    def _acquire(self, investigation, token):
        with self.store.transaction() as db:
            row = self.store._row(db, investigation)
            if row["context_fingerprint"] != self.evaluator.context_fingerprint:
                raise InvestigationError("Evaluator context does not match the saved investigation")
            if row["policy_fingerprint"] != self.evaluator.policy.fingerprint or FaultPolicy.model_validate_json(row["policy"]).fingerprint != row["policy_fingerprint"]:
                raise InvestigationError("Evaluator policy does not match the saved investigation")
            now = self._wall()
            if row["lease_token"] is not None and row["lease_expires"] is not None and row["lease_expires"] > now:
                raise InvestigationBusy("Another runner is executing this investigation")
            db.execute("UPDATE investigations SET lease_token=?, lease_expires=? WHERE id=?", (token, now + self._ttl(), investigation))
            # The previous lease is gone, so anything still in flight belongs to a dead runner.
            db.execute("DELETE FROM attempts WHERE investigation=? AND status='reserved'", (investigation,))
            orphans = [id for (id,) in db.execute("SELECT id FROM attempts WHERE investigation=? AND status='running' ORDER BY reserved",
                (investigation,))]
            for attempt in orphans:
                db.execute("UPDATE attempts SET status='interrupted', finished=?, reason=? WHERE id=?",
                    (now, "Runner stopped before recording a result", attempt))
            budget = InvestigationBudget.model_validate_json(row["budget"])
            self._settle_exhausted(db, investigation, budget)
        return budget, orphans

    def _owned(self, db, investigation, token):
        found = db.execute("SELECT lease_token, lease_expires, cancel_requested FROM investigations WHERE id=?", (investigation,)).fetchone()
        if found is None or found[0] != token or found[1] is None or found[1] <= self._wall():
            raise LeaseLost("Investigation lease was lost")
        return bool(found[2])

    def _heartbeat(self, investigation, token) -> bool:
        with self.store.transaction() as db:
            cancel = self._owned(db, investigation, token)
            db.execute("UPDATE investigations SET lease_expires=? WHERE id=?", (self._wall() + self._ttl(), investigation))
            return cancel

    def _unlock(self, investigation, token):
        with self.store.transaction() as db:
            db.execute("UPDATE investigations SET lease_token=NULL, lease_expires=NULL WHERE id=? AND lease_token=?", (investigation, token))

    def _finish(self, investigation, token, reason):
        with self.store.transaction() as db:
            self._owned(db, investigation, token)
            db.execute("UPDATE investigations SET stop_reason=? WHERE id=?", (reason, investigation))

    # ---- 1. validation and duplicates ------------------------------------------

    def _validate(self, investigation, token):
        rejected, duplicates = [], []
        with self.store.transaction() as db:
            self._owned(db, investigation, token)
            for id, payload in db.execute("SELECT id,payload FROM proposals WHERE investigation=? AND status='pending' AND scenario_id IS NULL"
                    " ORDER BY seq", (investigation,)).fetchall():
                try:
                    case = self._case(payload)
                except (ValueError, TypeError) as error:
                    db.execute("UPDATE proposals SET status='rejected', reason=? WHERE id=?", (_short(error), id))
                    rejected.append(id)
                    continue
                db.execute("UPDATE proposals SET scenario_id=? WHERE id=?", (case.scenario_id, id))
            # The earliest non-rejected proposal owns a scenario; later identical ones never run.
            owners = {}
            for id, scenario, status in db.execute("SELECT id,scenario_id,status FROM proposals WHERE investigation=? AND scenario_id IS NOT NULL"
                    " AND status!='rejected' ORDER BY seq", (investigation,)).fetchall():
                if scenario not in owners:
                    owners[scenario] = id
                elif status == "pending":
                    db.execute("UPDATE proposals SET status='duplicate', duplicate_of=?, reason=? WHERE id=?",
                        (owners[scenario], "Same scenario as an earlier proposal", id))
                    duplicates.append(id)
        return rejected, duplicates

    def _case(self, payload) -> FaultCase:
        if len(payload.encode()) > MAX_PROPOSAL_BYTES:
            raise ValueError("Proposal exceeds its size limit")
        case = FaultCase.model_validate_json(payload)
        self.evaluator.policy.check(case, self.evaluator.config)
        return case

    # ---- 2. admission ----------------------------------------------------------

    def _reserve(self, investigation, token, budget):
        """Check every limit and reserve a slot atomically, or return a stop reason."""
        with self.store.transaction() as db:
            if self._owned(db, investigation, token):
                return "cancelled"
            slots, failures = self.store._usage(db, investigation)
            if failures >= budget.max_failures:
                return "failure_limit"
            failed = dict(db.execute(f"SELECT proposal, COUNT(*) FROM attempts WHERE investigation=? AND status IN ({_marks(FAILURE_STATUSES)})"
                " GROUP BY proposal", (investigation, *FAILURE_STATUSES)).fetchall())
            pending = db.execute("SELECT id,payload,scenario_id,seq FROM proposals WHERE investigation=? AND status='pending'"
                " AND scenario_id IS NOT NULL", (investigation,)).fetchall()
            if not pending:
                return "completed"
            if slots >= budget.max_experiments:
                return "budget_exhausted"
            # Retry previously failed scenarios after untried ones.
            proposal, payload, scenario_id, _ = min(pending, key=lambda row: (failed.get(row[0], 0), row[3]))
            if self.evaluator.remaining_evaluations == 0 and not self.evaluator.is_cached(scenario_id):
                return "evaluator_budget"
            attempt = uuid.uuid4().hex
            db.execute("INSERT INTO attempts(id,investigation,proposal,scenario_id,status,lease_token,reserved) VALUES(?,?,?,?, 'reserved', ?, ?)",
                (attempt, investigation, proposal, scenario_id, token, self._wall()))
            db.execute("UPDATE investigations SET lease_expires=? WHERE id=?", (self._wall() + self._ttl(), investigation))
        return attempt, proposal, payload, scenario_id

    def _release(self, investigation, token, attempt):
        with self.store.transaction() as db:
            if db.execute("SELECT lease_token FROM investigations WHERE id=?", (investigation,)).fetchone()[0] == token:
                db.execute("DELETE FROM attempts WHERE id=? AND status='reserved' AND lease_token=?", (attempt, token))

    def _start(self, investigation, token, attempt):
        with self.store.transaction() as db:
            self._owned(db, investigation, token)
            db.execute("UPDATE attempts SET status='running', started=? WHERE id=? AND status='reserved'", (self._wall(), attempt))

    # ---- 3. execution and recording --------------------------------------------

    def _execute(self, investigation, token, attempt, proposal, payload, scenario_id, budget, should_stop, flags, deadline):
        try:
            case = self._case(payload)
            if case.scenario_id != scenario_id:
                raise ValueError("Proposal identity changed after validation")
            result = self.evaluator.evaluate(case, cancelled=should_stop)
            if (result.scenario_id != scenario_id or result.context_fingerprint != self.evaluator.context_fingerprint
                    or result.policy_fingerprint != self.evaluator.policy.fingerprint):
                raise ValueError("Evaluator returned a result for a different scenario or context")
            document = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(document.encode()) > MAX_RESULT_BYTES:
                raise ValueError("Evaluation result exceeds its storage limit")
        except EvaluationStopped as error:
            if flags["lost"]:
                raise LeaseLost("Investigation lease was lost") from error
            if flags["cancel"]:
                status, reason = "cancelled", "Cancelled during execution"
            elif self._monotonic() >= deadline:
                status, reason = "stopped", "Investigation time limit reached during execution"
            else:
                status, reason = "timed_out", _short(error)
            return self._record(investigation, token, attempt, proposal, status, reason, budget)
        except Exception as error:  # Any evaluator fault is a counted, recorded failure.
            return self._record(investigation, token, attempt, proposal, "failed", _short(error), budget)
        return self._record(investigation, token, attempt, proposal, "completed", None, budget, document)

    def _record(self, investigation, token, attempt, proposal, status, reason, budget, document=None):
        with self.store.transaction() as db:
            self._owned(db, investigation, token)
            db.execute("UPDATE attempts SET status=?, reason=?, finished=?, result=?, result_digest=? WHERE id=? AND status='running'",
                (status, reason, self._wall(), document, hashlib.sha256(document.encode()).hexdigest() if document else None, attempt))
            if status == "completed":
                db.execute("UPDATE proposals SET status='completed', reason=NULL WHERE id=?", (proposal,))
            elif status in FAILURE_STATUSES:
                self._settle_exhausted(db, investigation, budget)
        return status

    @staticmethod
    def _settle_exhausted(db, investigation, budget):
        db.execute(f"UPDATE proposals SET status='exhausted', reason=? WHERE investigation=? AND status='pending' AND id IN ("
            f"SELECT proposal FROM attempts WHERE investigation=? AND status IN ({_marks(FAILURE_STATUSES)})"
            " GROUP BY proposal HAVING COUNT(*) >= ?)",
            ("Failed attempt limit reached", investigation, investigation, *FAILURE_STATUSES, budget.max_attempts_per_scenario))
