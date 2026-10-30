"""Independent validation: a procedure frozen before assessment, applied once to histories it has never seen."""
from dataclasses import replace
import json
import time
from uuid import uuid4

from app.config import get_settings
from app.experiments.exposure import history_ids
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase
from app.investigator.controller import controllerStatus
from app.investigator.findings import classify, digest, loadCriterion, recordFindings
from app.investigator.reduction import ensureTable as ensureReductions
from app.models.train import FoldFit, TrainingResult, fit_final
from app.schemas import SplitAssignment

NOTE = ("Validation on histories outside the development context. The procedure was frozen before these histories were read; "
    "changing it after reading the results needs another set of fresh histories for a new independent claim.")


def ensureTables(db):
    db.execute("CREATE TABLE IF NOT EXISTS validations(id TEXT PRIMARY KEY, investigation TEXT NOT NULL REFERENCES investigation_runs(id),"
        " status TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS exposures(history TEXT PRIMARY KEY, source TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL)")


def freeze(store, investigation, *, remedyThreshold=None) -> dict:
    criterion = loadCriterion(store, investigation)
    if criterion is None:
        raise ValueError("Save a finding criterion before freezing a procedure")
    record = store.get(investigation)
    cases = {}
    for finding in recordFindings(store, investigation):
        if finding.is_discovery:
            cases.setdefault(finding.scenario_id, {"label": f"discovered:{finding.family}", "scenario": store.result(finding.attempt_id).scenario.model_dump(mode="json")})
    with store.transaction() as db:
        ensureReductions(db)
        ensureTables(db)
        for (payload,) in db.execute("SELECT payload FROM reductions WHERE investigation=? AND status IN ('complete','partial') ORDER BY created", (investigation,)):
            item = json.loads(payload)
            cases.setdefault(item["finalScenarioId"], {"label": f"reduced:{item['family']}", "scenario": item["final"]})
        if not cases:
            raise ValueError("Nothing to validate: the investigation has no measured failure or finished reduction")
        controller = controllerStatus(store, investigation)
        procedure = {"version": 1, "investigation": investigation, "context": record.context_fingerprint, "policy": record.policy.fingerprint,
            "criterion": criterion.model_dump(mode="json"), "cases": [{"scenarioId": key, **value} for key, value in sorted(cases.items())],
            "remedy": {"kind": "threshold", "threshold": remedyThreshold} if remedyThreshold is not None else None,
            "search": {key: controller["configuration"][key] for key in ("model", "prompt")} if controller else {"model": None, "prompt": None}}
        frozen = {"id": uuid4().hex, "status": "frozen", "procedure": procedure, "procedureDigest": digest(procedure), "frozenAt": time.time()}
        db.execute("INSERT INTO validations VALUES(?,?,?,?,?)", (frozen["id"], investigation, "frozen", json.dumps(frozen, sort_keys=True), frozen["frozenAt"]))
    return frozen


def loadValidation(store, validation):
    with store.transaction() as db:
        ensureTables(db)
        row = db.execute("SELECT payload FROM validations WHERE id=?", (validation,)).fetchone()
    if row is None:
        raise KeyError("Unknown validation")
    return json.loads(row[0])


def freshContext(evaluator, fresh, thresholds=None):
    # Models are refit on every development history and score only the fresh ones; the development guard of the evaluator still applies.
    training = evaluator.snapshot()
    if set(fresh.equipment_ids) & set(training.splits.development) or fresh.sensors != training.dataset.sensors:
        raise ValueError("Fresh histories need new equipment identifiers and the development sensors")
    candidates = {}
    for name in evaluator.thresholds:
        candidates[name], builder, preprocessor = fit_final(training.dataset, training.splits, training.specs[name], config=training.config)
    ids = list(fresh.equipment_ids)
    splits = SplitAssignment(holdout=[], development=ids, folds=[ids], seed=training.splits.seed, config_fingerprint=training.splits.config_fingerprint)
    result = TrainingResult(dataset=replace(fresh, config=training.config), splits=splits, folds=[FoldFit(0, [], ids, preprocessor, builder, candidates)],
        out_of_fold={}, specs=training.specs, config=training.config)
    return FixedDevelopmentEvaluator(result, thresholds or evaluator.thresholds, evaluator.policy)


def knownExposures(evaluator):
    training = evaluator.snapshot()
    known = {history: ("development", "Investigation development history") for history in history_ids(training.dataset, training.splits.development).values()}
    path = get_settings().bundle_path.parent / "history-identities.json"
    if path.is_file():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        known |= {history: ("benchmark", "Previously examined NASA FD001 history") for history in recorded["histories"].values()}
    return known


def assess(store, validation, evaluator, fresh) -> dict:
    frozen = loadValidation(store, validation)
    procedure = frozen["procedure"]
    if frozen["status"] != "frozen":
        raise ValueError("This procedure has already been assessed; a changed procedure needs another set of fresh histories")
    record = store.get(procedure["investigation"])
    record.check_context(evaluator)
    if digest(procedure) != frozen["procedureDigest"]:
        raise ValueError("The frozen procedure no longer matches its digest")
    identities = list(history_ids(fresh, fresh.equipment_ids).values())
    if len(set(identities)) != len(identities):
        raise ValueError("Repeated histories cannot count as independent equipment")
    with store.transaction() as db:
        ensureTables(db)
        db.executemany("INSERT OR IGNORE INTO exposures VALUES(?,?,?,?)", [(history, source, reason, time.time()) for history, (source, reason) in knownExposures(evaluator).items()])
        seen = [history for history in identities if db.execute("SELECT 1 FROM exposures WHERE history=?", (history,)).fetchone()]
        if seen:
            raise ValueError(f"{len(seen)} of these histories were already seen; use genuinely fresh histories")
        if db.execute("SELECT status FROM validations WHERE id=?", (validation,)).fetchone()[0] != "frozen":
            raise ValueError("This procedure has already been assessed")
        # Exposure is recorded before scoring, so an interrupted assessment still uses up these histories.
        db.executemany("INSERT INTO exposures VALUES(?,?,?,?)", [(history, validation, "Fresh validation history", time.time()) for history in identities])
        frozen["status"] = "assessing"
        db.execute("UPDATE validations SET status='assessing', payload=? WHERE id=?", (json.dumps(frozen, sort_keys=True), validation))

    criterion = loadCriterion(store, procedure["investigation"])
    started = time.monotonic()
    contexts = {"original": freshContext(evaluator, fresh)}
    if procedure["remedy"]:
        contexts["remedy"] = freshContext(evaluator, fresh, {criterion.candidate: procedure["remedy"]["threshold"]})
    clean = {label: context.cleanMetrics()[criterion.candidate] for label, context in contexts.items()}
    rows = []
    for case in procedure["cases"]:
        scenario = FaultCase.model_validate(case["scenario"])
        rows.append({"label": case["label"], "scenarioId": case["scenarioId"], **{label: summary(classify(context.evaluate(scenario), criterion))
            for label, context in contexts.items()}})
    frozen |= {"status": "assessed", "assessedAt": time.time(), "freshHistories": len(identities), "note": NOTE,
        "clean": {label: {"detection": item.detection_fraction, "alarmBurden": item.early_alarm_burden, "medianLead": item.median_lead_time,
            "histories": item.engines} for label, item in clean.items()}, "cases": rows, "elapsedSeconds": round(time.monotonic() - started, 3)}
    with store.transaction() as db:
        db.execute("UPDATE validations SET status='assessed', payload=? WHERE id=?", (json.dumps(frozen, sort_keys=True), validation))
    return frozen


def freshSynthetic(config, seed, count=12):
    """Synthetic histories from another seed with new identifiers, generated like the synthetic development context."""
    from app.data.synthetic import make_synthetic_dataset
    data = make_synthetic_dataset(n_equipment=count, min_life=85, max_life=100, seed=seed, config=config)
    frame = data.frame.copy()
    frame["equipment_id"] = f"FRESH{seed}-" + frame["equipment_id"]
    return replace(data, frame=frame, dataset_id=f"fresh-synthetic-{seed}")


def summary(finding):
    return {"status": finding.status, "evaluated": finding.evaluated_histories, "expected": finding.expected_histories, "coverage": finding.coverage,
        "cleanDetection": finding.clean_detection, "faultedDetection": finding.faulted_detection, "reproduced": finding.is_discovery}
