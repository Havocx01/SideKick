"""Deterministic classification of recorded experiment results."""
import hashlib
import json
import time
from typing import Literal

from pydantic import Field

from app.faults.evaluator import FaultEvaluation
from app.faults.investigation import FAILURE_STATUSES
from app.investigator.records import Frozen

FindingStatus = Literal["measured_failure", "no_measured_failure", "inconclusive", "not_applicable",
    "invalid_proposal", "execution_error"]
EffectKind = Literal["missed_warnings", "late_warnings", "alarm_burden"]
WarningState = Literal["detected", "late", "missed"]


class FindingCriterion(Frozen):
    version: Literal[1] = 1
    candidate: str = Field(min_length=1, max_length=256)
    min_coverage: float = Field(default=0.8, gt=0, le=1, description="Evaluated / expected development histories.")
    min_histories: int = Field(default=10, ge=1, le=1000, strict=True)
    min_clean_detection: float = Field(default=0.8, ge=0, le=1, description="Useful-warning fraction the clean model must reach on matched histories.")
    min_lost_warnings: int = Field(default=1, ge=1, le=1000, strict=True, description="Clean useful warnings that became missed or late.")
    max_alarm_burden: float = Field(default=0.05, ge=0, le=1, description="Highest acceptable early alarm burden.")
    min_burden_increase: float = Field(default=0.01, gt=0, le=1, description="Smallest consequential faulted-minus-clean burden increase.")

    @property
    def fingerprint(self) -> str:
        return digest(self.model_dump(mode="json"))


class HistorySupport(Frozen):
    equipment_id: str
    clean: WarningState
    faulted: WarningState
    clean_lead: int | None
    faulted_lead: int | None
    clean_episodes: int
    faulted_episodes: int


class Effect(Frozen):
    kind: EffectKind
    histories: tuple[str, ...]
    clean_value: float | None = Field(default=None, description="Matched clean aggregate for aggregate effects such as alarm burden.")
    faulted_value: float | None = None


class Finding(Frozen):
    version: Literal[1] = 1
    status: FindingStatus
    reasons: tuple[str, ...] = ()
    criterion: FindingCriterion
    criterion_fingerprint: str
    proposal_id: str | None = None
    attempt_id: str | None = None
    scenario_id: str | None = None
    evidence_digest: str | None = Field(default=None, description="SHA-256 of the canonical evaluation this finding was computed from.")
    context_fingerprint: str | None = None
    expected_histories: int | None = None
    evaluated_histories: int | None = None
    coverage: float | None = None
    clean_detection: float | None = None
    faulted_detection: float | None = None
    clean_burden: float | None = None
    faulted_burden: float | None = None
    assumptions: tuple[str, ...] = Field(default=(), description="Profile constraints the tested scenario relies on.")
    effects: tuple[Effect, ...] = Field(default=(), description="Observed effects; only a measured_failure is a discovery.")
    support: tuple[HistorySupport, ...] = Field(default=(), description="Matched histories whose warning outcome changed.")

    @property
    def is_discovery(self) -> bool:
        return self.status == "measured_failure"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def warningState(outcome) -> WarningState:
    return "detected" if outcome.detected else "late" if outcome.late else "missed"


def checkCriterion(criterion: FindingCriterion, thresholds) -> FindingCriterion:
    criterion = FindingCriterion.model_validate(criterion.model_dump(mode="json"))
    if criterion.candidate not in thresholds:
        raise ValueError("Finding criterion must target one of the investigation's fixed models")
    return criterion


def classify(evaluation: FaultEvaluation, criterion: FindingCriterion, *, proposal_id=None, attempt_id=None) -> Finding:
    criterion = FindingCriterion.model_validate(criterion.model_dump(mode="json"))
    evaluation = FaultEvaluation.model_validate(evaluation.model_dump(mode="json"))
    model = next((item for item in evaluation.models if item.candidate == criterion.candidate), None)
    if model is None:
        raise ValueError("Evaluation does not contain the criterion's target model")
    base = {"criterion": criterion, "criterion_fingerprint": criterion.fingerprint, "proposal_id": proposal_id,
        "attempt_id": attempt_id, "scenario_id": evaluation.scenario_id, "evidence_digest": digest(evaluation.model_dump(mode="json")),
        "context_fingerprint": evaluation.context_fingerprint, "expected_histories": evaluation.expected_histories,
        "assumptions": evaluation.policy.assumptionsFor(evaluation.scenario),
        "evaluated_histories": evaluation.evaluated_histories,
        "coverage": evaluation.evaluated_histories / evaluation.expected_histories if evaluation.expected_histories else 0.0}
    if evaluation.status == "not_applicable" or model.clean_matched is None or model.faulted is None or not model.pairs:
        return Finding(status="not_applicable", reasons=("No eligible history had changed scorable readings",), **base)
    clean, faulted = model.clean_matched, model.faulted
    base |= {"clean_detection": clean.detection_fraction, "faulted_detection": faulted.detection_fraction,
        "clean_burden": clean.early_alarm_burden, "faulted_burden": faulted.early_alarm_burden}

    reasons = []
    if base["coverage"] < criterion.min_coverage:
        reasons.append(f"Coverage {evaluation.evaluated_histories}/{evaluation.expected_histories} is below the required {criterion.min_coverage:g}")
    if evaluation.evaluated_histories < criterion.min_histories:
        reasons.append(f"{evaluation.evaluated_histories} eligible histories is below the required {criterion.min_histories}")
    if clean.detection_fraction < criterion.min_clean_detection:
        reasons.append("Clean model does not meet the useful-warning requirement on matched histories")
    if clean.early_alarm_burden is None or faulted.early_alarm_burden is None:
        reasons.append("Early alarm burden is unavailable")
    elif clean.early_alarm_burden > criterion.max_alarm_burden:
        reasons.append("Clean model already exceeds the acceptable alarm burden")

    support, missed, late, noisier = [], [], [], []
    for pair in sorted(model.pairs, key=lambda item: item.equipment_id):
        before, after = warningState(pair.clean), warningState(pair.faulted)
        if before == "detected" and after == "missed":
            missed.append(pair.equipment_id)
        elif before == "detected" and after == "late":
            late.append(pair.equipment_id)
        if pair.faulted.episode_count > pair.clean.episode_count:
            noisier.append(pair.equipment_id)
        if (before, pair.clean.lead_time, pair.clean.episode_count) != (after, pair.faulted.lead_time, pair.faulted.episode_count):
            support.append(HistorySupport(equipment_id=pair.equipment_id, clean=before, faulted=after,
                clean_lead=pair.clean.lead_time, faulted_lead=pair.faulted.lead_time,
                clean_episodes=pair.clean.episode_count, faulted_episodes=pair.faulted.episode_count))

    effects = []
    if len(missed) + len(late) >= criterion.min_lost_warnings:
        effects += [Effect(kind=kind, histories=tuple(ids)) for kind, ids in (("missed_warnings", missed), ("late_warnings", late)) if ids]
    if (clean.early_alarm_burden is not None and faulted.early_alarm_burden is not None
            and faulted.early_alarm_burden > criterion.max_alarm_burden
            and faulted.early_alarm_burden - clean.early_alarm_burden >= criterion.min_burden_increase):
        effects.append(Effect(kind="alarm_burden", histories=tuple(noisier),
            clean_value=clean.early_alarm_burden, faulted_value=faulted.early_alarm_burden))
    status = "inconclusive" if reasons else "measured_failure" if effects else "no_measured_failure"
    return Finding(status=status, reasons=tuple(reasons), effects=tuple(effects), support=tuple(support), **base)


def ensureTables(db):
    db.execute("CREATE TABLE IF NOT EXISTS finding_criteria(investigation TEXT PRIMARY KEY REFERENCES investigation_runs(id),"
        " version INTEGER NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS findings(investigation TEXT NOT NULL REFERENCES investigation_runs(id), subject TEXT NOT NULL,"
        " criterion_fingerprint TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(investigation, subject))")


def saveCriterion(store, investigation: str, criterion: FindingCriterion) -> FindingCriterion:
    # A different criterion needs a new investigation so earlier findings stay comparable.
    criterion = checkCriterion(criterion, {item.candidate for item in store.get(investigation).thresholds})
    with store.transaction() as db:
        ensureTables(db)
        store._row(db, investigation)
        saved = db.execute("SELECT fingerprint FROM finding_criteria WHERE investigation=?", (investigation,)).fetchone()
        if saved is not None:
            if saved[0] != criterion.fingerprint:
                raise ValueError("This investigation already has a different finding criterion")
            return criterion
        db.execute("INSERT INTO finding_criteria VALUES(?,?,?,?,?)",
            (investigation, criterion.version, criterion.fingerprint, criterion.model_dump_json(), time.time()))
    return criterion


def loadCriterion(store, investigation: str) -> FindingCriterion | None:
    with store.transaction() as db:
        ensureTables(db)
        row = db.execute("SELECT fingerprint, payload FROM finding_criteria WHERE investigation=?", (investigation,)).fetchone()
    if row is None:
        return None
    criterion = FindingCriterion.model_validate_json(row[1])
    if criterion.fingerprint != row[0]:
        raise ValueError("Saved finding criterion does not match its fingerprint")
    return criterion


def classifyInvestigation(store, investigation: str) -> list[Finding]:
    # Pending, duplicate and stopped work is not a finding.
    criterion = loadCriterion(store, investigation)
    if criterion is None:
        raise ValueError("Save a finding criterion for this investigation first")
    state = store.load(investigation)
    base = {"criterion": criterion, "criterion_fingerprint": criterion.fingerprint}
    findings = []
    for proposal in state.proposals:
        if proposal.status == "rejected":
            findings.append(Finding(status="invalid_proposal", proposal_id=proposal.id, reasons=(proposal.reason or "Rejected",), **base))
    for attempt in state.attempts:
        if attempt.status == "completed":
            evaluation = store.result(attempt.id)
            if evaluation.context_fingerprint != state.context_fingerprint:
                raise ValueError("Recorded result does not belong to this investigation")
            findings.append(classify(evaluation, criterion, proposal_id=attempt.proposal_id, attempt_id=attempt.id))
        elif attempt.status in FAILURE_STATUSES:
            findings.append(Finding(status="execution_error", proposal_id=attempt.proposal_id, attempt_id=attempt.id,
                scenario_id=attempt.scenario_id, reasons=(attempt.reason or attempt.status,), **base))
    return findings


def recordFindings(store, investigation: str) -> list[Finding]:
    findings = classifyInvestigation(store, investigation)
    with store.transaction() as db:
        ensureTables(db)
        saved = dict(db.execute("SELECT subject, payload FROM findings WHERE investigation=?", (investigation,)).fetchall())
        for finding in findings:
            subject, payload = finding.attempt_id or finding.proposal_id, finding.model_dump_json()
            if subject in saved and saved[subject] != payload:
                raise ValueError("A saved finding no longer matches its recorded evidence")
            if subject not in saved:
                db.execute("INSERT INTO findings VALUES(?,?,?,?,?)", (investigation, subject, finding.criterion_fingerprint, finding.status, payload))
    return findings


def summarize(findings) -> dict:
    counts = {}
    for finding in findings:
        counts[finding.status] = counts.get(finding.status, 0) + 1
    return {"counts": counts, "discoveries": [finding.attempt_id for finding in findings if finding.is_discovery]}
