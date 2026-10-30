"""Compare executable remedies against the original fixed context."""
import json
import time
from uuid import uuid4

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.investigation import ExperimentRunner
from app.faults.scenarios import FaultCase
from app.investigator.findings import classify, loadCriterion, recordFindings
from app.investigator.reduction import ensureTable as ensureReductions

REMEDIES = {
    "threshold": "Use an explicitly chosen warning threshold for the target model with the same fitted models.",
    "augmented": "Retrain the development folds with sampled sensor-fault augmentation and select its threshold on clean predictions.",
}


class RemedyError(RuntimeError):
    pass


def thresholdRemedy(evaluator, candidate, threshold):
    thresholds = {candidate: float(threshold)}
    return FixedDevelopmentEvaluator(evaluator.snapshot(), thresholds, evaluator.policy), candidate


def augmentedRemedy(evaluator, *, approveTraining=False):
    if not approveTraining:
        raise PermissionError("Augmented retraining needs explicit approval")
    from app.models.candidates import AugmentedXGBoostCandidate
    from app.models.train import train_development
    from app.scoring.pipeline import pick_thresholds
    from app.scoring.selection import default_criteria
    snapshot = evaluator.snapshot()
    config = snapshot.config
    # Development-only retraining on the same folds; reserved histories are never used.
    training = train_development(snapshot.dataset, config=config, splits=snapshot.splits, candidates=[AugmentedXGBoostCandidate("remedy", {"n_estimators": 120})])
    choices = pick_thresholds(training, default_criteria(config), config=config)
    name = next(iter(choices))
    return FixedDevelopmentEvaluator(training, {name: choices[name].threshold}, evaluator.policy), name


def ensureTable(db):
    db.execute("CREATE TABLE IF NOT EXISTS remedies(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES investigation_runs(id),"
        " kind TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL)")


def caseSuite(store, investigation, evaluator, regressions):
    cases = []
    # Previously passing cases show what a remedy costs elsewhere.
    for finding in recordFindings(store, investigation):
        if finding.attempt_id and finding.status != "execution_error":
            label = "discovered" if finding.is_discovery else "tested"
            cases.append({"label": f"{label}:{finding.family}", "source": finding.attempt_id, "scenario": store.result(finding.attempt_id).scenario})
    with store.transaction() as db:
        ensureReductions(db)
        rows = db.execute("SELECT id, payload FROM reductions WHERE investigation=? AND status IN ('complete','partial') ORDER BY created", (investigation,)).fetchall()
    for reduction, payload in rows:
        cases.append({"label": f"reduced:{json.loads(payload)['family']}", "source": reduction, "scenario": FaultCase.model_validate(json.loads(payload)["final"])})
    for regression in regressions:
        if regression["contextFingerprint"] != evaluator.context_fingerprint or regression["policyFingerprint"] != evaluator.policy.fingerprint:
            raise RemedyError("Regression case belongs to a different fitted context or policy")
        cases.append({"label": f"regression:{regression['family']}", "source": regression["source"]["reduction"],
            "scenario": FaultCase.model_validate(regression["scenario"])})
    unique = {}
    for case in cases:
        unique.setdefault(case["scenario"].scenario_id, case)
    return list(unique.values())


def outcome(evaluation, finding, candidate):
    model = next(item for item in evaluation.models if item.candidate == candidate)
    faulted = model.faulted
    return {"status": finding.status, "evaluated": evaluation.evaluated_histories, "exclusions": len(evaluation.exclusions),
        "cleanDetection": finding.clean_detection, "faultedDetection": finding.faulted_detection,
        "cleanBurden": finding.clean_burden, "faultedBurden": finding.faulted_burden,
        "faultedMedianLead": faulted.median_lead_time if faulted else None}, sorted(pair.equipment_id for pair in model.pairs)


def cleanSummary(metrics):
    return {"detection": metrics.detection_fraction, "alarmBurden": metrics.early_alarm_burden, "medianLead": metrics.median_lead_time,
        "histories": metrics.engines}


def stillFailing(rows):
    return sum(row["original"]["status"] == row["remedy"]["status"] == "measured_failure" for row in rows)


def compareRemedy(store, evaluator, investigation, kind, *, threshold=None, approveTraining=False, regressions=()) -> dict:
    if kind not in REMEDIES:
        raise RemedyError(f"Unknown remedy: {kind}")
    criterion = loadCriterion(store, investigation)
    if criterion is None:
        raise RemedyError("Save a finding criterion before comparing remedies")
    store.get(investigation).check_context(evaluator)

    with ExperimentRunner(store, evaluator).lease(investigation):
        cases = caseSuite(store, investigation, evaluator, regressions)
        if not any(case["label"].split(":")[0] in {"discovered", "reduced", "regression"} for case in cases):
            raise RemedyError("No measured failure, reduction or regression case to compare")
        started = time.monotonic()
        if kind == "threshold":
            if threshold is None:
                raise RemedyError("A threshold remedy needs an explicit threshold")
            remedy, remedyCandidate = thresholdRemedy(evaluator, criterion.candidate, threshold)
        else:
            remedy, remedyCandidate = augmentedRemedy(evaluator, approveTraining=approveTraining)
        prepareSeconds = time.monotonic() - started

        remedyCriterion = criterion.model_copy(update={"candidate": remedyCandidate})
        rows = []
        started = time.monotonic()
        for case in cases:
            original, changed = evaluator.evaluate(case["scenario"]), remedy.evaluate(case["scenario"])
            before, beforeCohort = outcome(original, classify(original, criterion), criterion.candidate)
            after, afterCohort = outcome(changed, classify(changed, remedyCriterion), remedyCandidate)
            rows.append({"label": case["label"], "source": case["source"], "scenarioId": case["scenario"].scenario_id,
                "original": before, "remedy": after, "matchedCohort": beforeCohort == afterCohort,
                "improved": before["status"] == "measured_failure" and after["status"] == "no_measured_failure" and beforeCohort == afterCohort,
                "degraded": before["status"] != "measured_failure" and after["status"] == "measured_failure"})
        evaluateSeconds = time.monotonic() - started

    clean = {"original": cleanSummary(evaluator.cleanMetrics()[criterion.candidate]), "remedy": cleanSummary(remedy.cleanMetrics()[remedyCandidate])}
    meets = (clean["remedy"]["detection"] >= criterion.min_clean_detection and clean["remedy"]["alarmBurden"] is not None
        and clean["remedy"]["alarmBurden"] <= criterion.max_alarm_burden and not any(row["degraded"] for row in rows))
    report = {"id": uuid4().hex, "investigation": investigation, "kind": kind, "description": REMEDIES[kind],
        "threshold": threshold, "originalContext": evaluator.context_fingerprint, "remedyContext": remedy.context_fingerprint,
        "originalCandidate": criterion.candidate, "remedyCandidate": remedyCandidate, "criterion": criterion.fingerprint,
        "cases": rows, "clean": clean, "improved": sum(row["improved"] for row in rows), "degraded": sum(row["degraded"] for row in rows),
        "stillFailing": stillFailing(rows), "meetsCriteria": meets, "cost": {"prepareSeconds": round(prepareSeconds, 3), "evaluateSeconds": round(evaluateSeconds, 3)},
        "note": "Development-only comparison. The remedy was chosen with these cases, so it needs fresh validation; no deployed model was changed."}
    with store.transaction() as db:
        ensureTable(db)
        db.execute("INSERT INTO remedies VALUES(?,?,?,?,?)", (report["id"], investigation, kind, json.dumps(report, sort_keys=True), time.time()))
    return report
