"""Public investigation evidence: aggregate results without private data."""
import json
import time

from app.faults.scenarios import FaultCase
from app.investigator.controller import controllerStatus
from app.investigator.findings import digest, family, loadCriterion, recordFindings
from app.investigator.reduction import ensureTable as ensureReductions
from app.investigator.remedies import ensureTable as ensureRemedies

NOTICE = ("Aggregate development evidence. The objective, equipment identifiers, raw readings, fitted models and keys are excluded. "
    "The digest shows this file is unchanged, not who made it or that it may be disclosed.")


def experimentRow(finding, number):
    return {"ref": f"result-{number}", "scenarioId": finding.scenario_id, "family": finding.family, "status": finding.status,
        "evaluatedHistories": finding.evaluated_histories, "expectedHistories": finding.expected_histories, "coverage": finding.coverage,
        "cleanDetection": finding.clean_detection, "faultedDetection": finding.faulted_detection,
        "cleanBurden": finding.clean_burden, "faultedBurden": finding.faulted_burden, "reasons": list(finding.reasons),
        "effects": [{"kind": effect.kind, "histories": len(effect.histories)} for effect in finding.effects],
        "changedHistories": len(finding.support), "assumptions": list(finding.assumptions)}


def adaptation(store, investigation, state, refs, chosen):
    # A model proposal adapts when it cites results that existed before it was made; repeating a family is reported, not hidden.
    attemptSeq = {item.id: next(proposal.seq for proposal in state.proposals if proposal.id == item.proposal_id) for item in state.attempts}
    with store.connection() as db:
        payloads = db.execute("SELECT id, seq, payload FROM proposals WHERE investigation=? ORDER BY seq", (investigation,)).fetchall()
    rows, seen = [], set()
    for proposalId, seq, payload in payloads:
        data = json.loads(payload)
        scenario = data.get("scenario", data)
        caseFamily = family(FaultCase.model_validate(scenario))
        if proposalId in chosen:
            basedOn = list((data.get("hypothesis") or {}).get("basedOn", []))
            rows.append({"proposal": seq, "family": caseFamily, "basedOn": [refs.get(item, "unrecorded") for item in basedOn],
                "basisRecorded": all(attemptSeq.get(item, seq) < seq and item in refs for item in basedOn), "newFamily": caseFamily not in seen})
        seen.add(caseFamily)
    return rows


def publicExport(store, investigation, *, contextName=None) -> dict:
    record = store.get(investigation)
    state = store.load(investigation)
    criterion = loadCriterion(store, investigation)
    findings = recordFindings(store, investigation) if criterion else []
    scenarios = {item.id: store.result(item.id).scenario for item in state.attempts if item.status == "completed"}
    measured = [finding for finding in findings if finding.attempt_id in scenarios]
    with store.transaction() as db:
        ensureReductions(db)
        ensureRemedies(db)
        reductions = [json.loads(row[0]) for row in db.execute("SELECT payload FROM reductions WHERE investigation=? ORDER BY created", (investigation,))]
        remedies = [json.loads(row[0]) for row in db.execute("SELECT payload FROM remedies WHERE investigation=? ORDER BY created", (investigation,))]

    profile = record.policy.profile
    controller = controllerStatus(store, investigation)
    chosen = {call["proposalId"] for call in controller["calls"] if call.get("proposalId")} if controller else set()
    attemptOf = {finding.attempt_id: number for number, finding in enumerate(measured, 1)}
    proposalOf = {item.id: item.proposal_id for item in state.attempts}
    content = {
        "version": 1, "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "notice": NOTICE,
        "context": {"fingerprint": record.context_fingerprint, "configFingerprint": record.config_fingerprint, "partition": record.partition,
            "thresholds": {item.candidate: item.threshold for item in record.thresholds}, "policyFingerprint": record.policy.fingerprint,
            "bounds": {"maxComponents": record.policy.max_components, "maxSeveritySd": record.policy.max_severity_sd,
                "maxDuration": record.policy.max_duration, "maxOnset": record.policy.max_onset, "allowedGroups": [list(group) for group in record.policy.allowed_groups]},
            "profile": {"id": profile.id, "version": profile.version, "equipment": profile.equipment, "synthetic": profile.synthetic,
                "constraints": [item.model_dump(mode="json") for item in profile.constraints]} if profile else None,
            "assumptions": record.policy.assumptions},
        "criterion": criterion.model_dump(mode="json") if criterion else None,
        "budget": {"maxExperiments": state.budget.max_experiments, "experimentsUsed": state.slots_used, "failures": state.failures, "stopReason": state.stop_reason},
        "proposals": {"total": len(state.proposals), "rejected": sum(item.status == "rejected" for item in state.proposals),
            "duplicates": sum(item.status == "duplicate" for item in state.proposals)},
        "experiments": [{**experimentRow(finding, number), "scenario": scenarios[finding.attempt_id].model_dump(mode="json"),
            "chosenBy": "nemotron" if proposalOf[finding.attempt_id] in chosen else "supplied"} for number, finding in enumerate(measured, 1)],
        "executionErrors": [{"status": finding.status, "scenarioId": finding.scenario_id} for finding in findings if finding.status == "execution_error"],
        "discoveryFamilies": sorted({finding.family for finding in measured if finding.is_discovery}),
        "controller": {key: controller[key] for key in ("stopReason", "modelStopReason", "callsUsed", "reservedCompletionTokens", "reportedCompletionTokens")}
            | {"model": controller["configuration"]["model"], "prompt": controller["configuration"]["prompt"],
                "reasoningEffort": controller["configuration"]["reasoningEffort"],
                "adaptation": adaptation(store, investigation, state, {attempt: f"result-{number}" for attempt, number in attemptOf.items()}, chosen)} if controller else None,
        "reductions": [{"status": item["status"], "original": item["original"], "final": item["final"], "family": item.get("family"),
            "claims": item["claims"], "experiments": item["experiments"],
            "steps": [{"change": step["change"], "status": step["status"], "accepted": step["accepted"], "evaluated": step.get("evaluated"),
                "cohortChanged": step.get("cohortChanged")} for step in item["steps"]]} for item in reductions],
        "remedies": [{"kind": item["kind"], "threshold": item["threshold"], "improved": item["improved"], "degraded": item["degraded"],
            "meetsCriteria": item["meetsCriteria"], "clean": item["clean"], "remedyContext": item["remedyContext"],
            "cases": [{"label": row["label"], "scenarioId": row["scenarioId"], "original": row["original"], "remedy": row["remedy"],
                "matchedCohort": row["matchedCohort"], "improved": row["improved"], "degraded": row["degraded"]} for row in item["cases"]],
            "note": item["note"]} for item in remedies],
        "reproduction": reproduction(profile, contextName),
    }
    return {**content, "digest": digest(content)}


def reproduction(profile, contextName):
    if profile is None or not profile.synthetic:
        return {"public": False, "note": "These results come from non-distributable data. Share the method, not the package."}
    name = contextName or "synthetic"
    return {"public": True, "steps": [
        f"python scripts/evaluate_fault_scenarios.py --profile {profile.id} --output artifacts/investigations/contexts/{name}",
        "Create an investigation with the criterion above and the listed scenarios as proposals, then run it.",
        "Compare each result's scenarioId and finding status with this file."]}

