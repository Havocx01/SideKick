"""Deterministic reduction of measured failures to simpler reproducible cases."""
import json
import time
from uuid import uuid4

from app.faults.evaluator import EvaluationStopped
from app.faults.investigation import ExperimentRunner
from app.faults.scenarios import FaultCase
from app.investigator.findings import FindingCriterion, classify, family, loadCriterion

SEVERITIES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
LENGTHS = (5, 10, 20, 40, 80)


class ReductionError(RuntimeError):
    pass


class Exhausted(Exception):
    pass


def ensureTable(db):
    db.execute("CREATE TABLE IF NOT EXISTS reductions(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES investigation_runs(id),"
        " source_attempt TEXT NOT NULL REFERENCES attempts(id), status TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)")


def changed(case, sensor, **values):
    data = case.model_dump(mode="json")
    for atom in data["components"]:
        if atom["sensor"] == sensor:
            atom.update(values)
    return FaultCase.model_validate(data)


def grids(atom, config, maxOnset):
    # Ascending order: the first passing value is the smallest passing value on the grid, monotonic or not.
    # A shorter drift ramp is more abrupt, not simpler, so ramps are left alone.
    if atom.severity_sd is not None:
        yield "severity_sd", [value for value in SEVERITIES if value < atom.severity_sd]
    if atom.length is not None:
        yield "length", [value for value in LENGTHS if value < atom.length]
    if atom.onset_before_failure is not None:
        start = -(-config.min_useful_lead // 10) * 10
        yield "onset_before_failure", [value for value in range(start, min(atom.onset_before_failure, maxOnset + 1), 10)]


def save(store, reduction):
    reduction["updated"] = time.time()
    with store.transaction() as db:
        db.execute("UPDATE reductions SET status=?, payload=?, updated=? WHERE id=?",
            (reduction["status"], json.dumps(reduction, sort_keys=True), reduction["updated"], reduction["id"]))


def loadReduction(store, reduction):
    with store.transaction() as db:
        ensureTable(db)
        row = db.execute("SELECT payload FROM reductions WHERE id=?", (reduction,)).fetchone()
    if row is None:
        raise KeyError("Unknown reduction")
    return json.loads(row[0])


def reduce(store, evaluator, attempt, *, maxExperiments=16, cancelled=None) -> dict:
    investigation = investigationOf(store, attempt)
    criterion = loadCriterion(store, investigation)
    if criterion is None:
        raise ReductionError("Save a finding criterion before reducing")
    source = store.result(attempt)
    store.get(investigation).check_context(evaluator)
    if not 1 <= maxExperiments <= evaluator.policy.max_evaluations:
        raise ReductionError("Reduction allowance is outside the evaluation policy")
    original = classify(source, criterion, attempt_id=attempt)
    if not original.is_discovery:
        raise ReductionError("Only a measured failure can be reduced")

    runner = ExperimentRunner(store, evaluator)
    with runner.lease(investigation) as token:
        def shouldStop():
            return runner.renewLease(investigation, token) or bool(cancelled and cancelled())

        with store.transaction() as db:
            ensureTable(db)
            db.execute("UPDATE reductions SET status='interrupted' WHERE investigation=? AND status='running'", (investigation,))
            reduction = {"id": uuid4().hex, "investigation": investigation, "sourceAttempt": attempt, "criterion": criterion.fingerprint,
                "status": "running", "original": source.scenario.model_dump(mode="json"), "final": None, "claims": [], "experiments": 0,
                "maxExperiments": maxExperiments, "steps": []}
            now = time.time()
            db.execute("INSERT INTO reductions VALUES(?,?,?,?,?,?,?)", (reduction["id"], investigation, attempt, "running", json.dumps(reduction), now, now))
        try:
            return runReduction(store, evaluator, criterion, source, reduction, shouldStop)
        except BaseException:
            if reduction["status"] == "running":
                reduction["status"] = "interrupted"
                save(store, reduction)
            raise


def investigationOf(store, attempt):
    with store.connection() as db:
        row = db.execute("SELECT investigation FROM attempts WHERE id=?", (attempt,)).fetchone()
    if row is None:
        raise KeyError("Unknown experiment attempt")
    return row[0]


def runReduction(store, evaluator, criterion: FindingCriterion, source, reduction, cancelled):
    cohort = cohortOf(source, criterion)

    def test(case, change):
        if cancelled is not None and cancelled():
            raise EvaluationStopped("Reduction cancelled")
        try:
            evaluator.policy.check(case, evaluator.config)
        except ValueError as error:
            reduction["steps"].append({"change": change, "scenario": case.model_dump(mode="json"), "status": "invalid_case", "reason": str(error), "accepted": False})
            return False
        if not evaluator.is_cached(case.scenario_id):
            if reduction["experiments"] >= reduction["maxExperiments"] or evaluator.remaining_evaluations == 0:
                raise Exhausted()
            reduction["experiments"] += 1
        result = evaluator.evaluate(case, cancelled=cancelled)
        if cancelled is not None and cancelled():
            raise EvaluationStopped("Reduction cancelled")
        finding = classify(result, criterion)
        accepted = finding.is_discovery
        reduction["steps"].append({"change": change, "scenario": case.model_dump(mode="json"), "scenarioId": case.scenario_id,
            "status": finding.status, "evidenceDigest": finding.evidence_digest, "evaluated": result.evaluated_histories,
            "cohortChanged": cohortOf(result, criterion) != cohort, "accepted": accepted})
        save(store, reduction)
        return accepted

    case = source.scenario
    removalsComplete = gridsTested = False
    try:
        if not test(case, "reproduce original"):
            reduction["status"] = "not_reproduced"
            save(store, reduction)
            return reduction
        progress = True
        while progress and len(case.components) > 1:
            progress = False
            for atom in case.components:
                smaller = FaultCase(components=[item for item in case.components if item.sensor != atom.sensor])
                if test(smaller, f"remove {atom.sensor}"):
                    case, progress = smaller, True
                    break
        removalsComplete = True
        tested = []
        for atom in case.components:
            for field, values in grids(atom, evaluator.config, evaluator.policy.max_onset):
                for value in values:
                    candidate = changed(case, atom.sensor, **{field: value})
                    if test(candidate, f"set {atom.sensor} {field} to {value}"):
                        case = candidate
                        break
                tested.append(f"{atom.sensor} {field}")
        gridsTested = True
        reduction["status"] = "complete"
    except Exhausted:
        reduction["status"] = "partial"
    except EvaluationStopped:
        reduction["status"] = "cancelled"

    reduction["final"] = case.model_dump(mode="json")
    reduction["finalScenarioId"] = case.scenario_id
    reduction["family"] = family(case)
    if removalsComplete:
        reduction["claims"].append("Component-minimal under tested single-component removals.")
    if gridsTested:
        reduction["claims"].append("Minimal on the tested grid for: " + ", ".join(tested) + "." if tested else "No grid parameters to simplify.")
    reduction["claims"].append("Not a proof of a global minimum.")
    save(store, reduction)
    return reduction


def cohortOf(result, criterion):
    model = next((item for item in result.models if item.candidate == criterion.candidate), None)
    return sorted(pair.equipment_id for pair in model.pairs) if model else []


def regressionCase(store, reduction) -> dict:
    saved = loadReduction(store, reduction)
    if saved["status"] not in {"complete", "partial"}:
        raise ReductionError("Only a finished reduction can become a regression case")
    criterion = loadCriterion(store, saved["investigation"])
    record = store.get(saved["investigation"])
    return {"version": 1, "scenario": saved["final"], "scenarioId": saved["finalScenarioId"], "family": saved["family"],
        "criterion": criterion.model_dump(mode="json"), "expected": "measured_failure", "claims": saved["claims"],
        "contextFingerprint": record.context_fingerprint, "policyFingerprint": record.policy.fingerprint,
        "profile": record.policy.profile.id if record.policy.profile else None,
        "source": {"investigation": saved["investigation"], "attempt": saved["sourceAttempt"], "reduction": saved["id"]}}
