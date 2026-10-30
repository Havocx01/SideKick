"""Strategy-neutral search benchmark on one fixed development context."""
import json
import time

import numpy as np

from app.faults.investigation import FAILURE_STATUSES
from app.faults.scenarios import FaultCase
from app.investigator.controller import controllerStatus
from app.investigator.findings import classify, family
from app.investigator.reduction import ensureTable as ensureReductions
from app.investigator.search import fixedSuite, neighbor, randomCase

DEDUP_RULE = "A discovery family is the sorted set of sensor:kind pairs; timing and severity are ignored."


def fixedStrategy(policy, config, rng):
    queue = fixedSuite(policy, config)
    return lambda history: queue.pop(0) if queue else None


def randomStrategy(policy, config, rng):
    return lambda history: randomCase(policy, config, rng)


def climbStrategy(policy, config, rng):
    # (1+1) hill climbing on the discrete encoding, restarting at random one time in five.
    def propose(history):
        scored = [item for item in history if item["drop"] is not None]
        if not scored or rng.random() < .2:
            return randomCase(policy, config, rng)
        best = max(scored, key=lambda item: (item["drop"], item["lost"], -item["experiment"]))
        tested = {json.dumps(item["case"], sort_keys=True) for item in history}
        for _ in range(20):
            candidate = neighbor(best["case"], policy, config, rng)
            if json.dumps(FaultCase.model_validate(candidate).model_dump(mode="json"), sort_keys=True) not in tested:
                return candidate
        return randomCase(policy, config, rng)
    return propose


STRATEGIES = {"fixed": fixedStrategy, "random": randomStrategy, "climb": climbStrategy}


def runStrategy(evaluator, criterion, propose, budget, seedCases=()):
    policy, config = evaluator.policy, evaluator.config
    history, seen = [], set()
    counts = {"proposals": 0, "infeasible": 0, "duplicates": 0, "errors": 0}
    pending = list(seedCases)
    started = time.monotonic()
    while len(history) < budget and counts["proposals"] < budget * 4:
        data = pending.pop(0) if pending else propose(history)
        if data is None:
            break
        data = data.get("scenario", data)
        counts["proposals"] += 1
        try:
            case = FaultCase.model_validate(data)
            policy.check(case, config)
        except ValueError:
            counts["infeasible"] += 1
            continue
        if case.scenario_id in seen:
            counts["duplicates"] += 1
            continue
        seen.add(case.scenario_id)
        try:
            finding = classify(evaluator.evaluate(case), criterion)
        except (ValueError, RuntimeError):
            counts["errors"] += 1
            continue
        history.append(entry(len(history) + 1, case, finding))
    return outcome(history, counts, time.monotonic() - started, 0)


def entry(number, case, finding):
    drop = finding.clean_detection - finding.faulted_detection if finding.faulted_detection is not None else None
    lost = sum(len(effect.histories) for effect in finding.effects if effect.kind != "alarm_burden")
    return {"experiment": number, "case": case.model_dump(mode="json"), "family": family(case), "status": finding.status, "drop": drop, "lost": lost,
        "coverage": finding.coverage}


def outcome(history, counts, elapsed, providerCalls, **extra):
    discoveries = [item for item in history if item["status"] == "measured_failure"]
    measured = [item for item in history if item["status"] in {"measured_failure", "no_measured_failure"}]
    return {"experiments": len(history), **counts,
        "feasibleRate": (counts["proposals"] - counts["infeasible"]) / counts["proposals"] if counts["proposals"] else None,
        "discoveries": len(discoveries), "discoveryFamilies": sorted({item["family"] for item in discoveries}),
        "firstDiscovery": discoveries[0]["experiment"] if discoveries else None,
        "strongestDrop": max((item["drop"] for item in measured), default=None),
        "mostLostWarnings": max((item["lost"] for item in measured), default=0),
        "meanCoverage": float(np.mean([item["coverage"] for item in history])) if history else None,
        "familiesTested": len({item["family"] for item in history}),
        "elapsedSeconds": round(elapsed, 3), "providerCalls": providerCalls, "reductionExperiments": 0, **extra}


def suppliedCases(store, investigation):
    # The cases a recorded run started from, so every strategy gets the same initial evidence.
    chosen = {call["proposalId"] for call in controllerStatus(store, investigation)["calls"] if call["proposalId"]}
    with store.connection() as db:
        rows = db.execute("SELECT id, payload FROM proposals WHERE investigation=? ORDER BY seq", (investigation,)).fetchall()
    return [json.loads(payload) for proposal, payload in rows if proposal not in chosen]


def recordedRun(store, investigation, criterion):
    """The saved controller run as it happened: nothing is re-executed, and every call, rejection and failure counts."""
    state, controller = store.load(investigation), controllerStatus(store, investigation)
    if controller is None:
        raise ValueError("This investigation has no recorded controller run")
    rejectedCalls = sum(call["status"] == "rejected" for call in controller["calls"])
    counts = {"proposals": len(state.proposals) + rejectedCalls, "infeasible": rejectedCalls + sum(item.status == "rejected" for item in state.proposals),
        "duplicates": sum(item.status == "duplicate" for item in state.proposals),
        "errors": sum(item.status in FAILURE_STATUSES for item in state.attempts)}
    completed = [store.result(item.id) for item in state.attempts if item.status == "completed"]
    history = [entry(number, result.scenario, classify(result, criterion)) for number, result in enumerate(completed, 1)]
    callSeconds = sum(call["elapsedSeconds"] or 0 for call in controller["calls"])
    runSeconds = sum(item.finished_at - item.started_at for item in state.attempts if item.started_at and item.finished_at)
    with store.transaction() as db:
        ensureReductions(db)
        rows = db.execute("SELECT payload FROM reductions WHERE investigation=?", (investigation,)).fetchall()
    reductionWork = sum(json.loads(row[0])["experiments"] for row in rows)
    configuration = controller["configuration"]
    return outcome(history, counts, callSeconds + runSeconds, controller["callsUsed"], reductionExperiments=reductionWork, invalidReplies=rejectedCalls,
        reservedCompletionTokens=controller["reservedCompletionTokens"], reportedCompletionTokens=controller["reportedCompletionTokens"],
        model=configuration["model"], prompt=configuration["prompt"])


def benchmark(contexts, criterion, strategies, *, budget=16, seeds=(0, 1, 2), seedCases=(), recorded=None) -> dict:
    """contexts maps a label to a factory returning a fresh evaluator, so no strategy reuses another's cache."""
    runs = [{"context": label, "strategy": "nemotron", "seed": None, **run} for label, run in (recorded or {}).items()]
    for label, makeEvaluator in contexts.items():
        for name, factory in strategies.items():
            for seed in seeds:
                evaluator = makeEvaluator()
                propose = factory(evaluator.policy, evaluator.config, np.random.default_rng(seed))
                runs.append({"context": label, "strategy": name, "seed": seed, **runStrategy(evaluator, criterion, propose, budget, seedCases)})

    summary = {}
    for name in dict.fromkeys(run["strategy"] for run in runs):
        rows = [run for run in runs if run["strategy"] == name]
        found = [run["firstDiscovery"] for run in rows if run["firstDiscovery"] is not None]
        drops = [run["strongestDrop"] for run in rows if run["strongestDrop"] is not None]
        summary[name] = {"runs": len(rows), "meanDiscoveryFamilies": float(np.mean([len(run["discoveryFamilies"]) for run in rows])),
            "uniqueDiscoveryFamilies": len({item for run in rows for item in run["discoveryFamilies"]}),
            "runsWithDiscovery": len(found), "meanFirstDiscovery": float(np.mean(found)) if found else None,
            "meanStrongestDrop": float(np.mean(drops)) if drops else None,
            "meanFeasibleRate": float(np.mean([run["feasibleRate"] for run in rows if run["feasibleRate"] is not None])),
            "duplicates": sum(run["duplicates"] for run in rows), "errors": sum(run["errors"] for run in rows),
            "meanElapsedSeconds": float(np.mean([run["elapsedSeconds"] for run in rows])),
            "providerCalls": sum(run["providerCalls"] for run in rows), "reductionExperiments": sum(run["reductionExperiments"] for run in rows),
            "invalidReplies": sum(run.get("invalidReplies", 0) for run in rows), "reportedCompletionTokens": sum(run.get("reportedCompletionTokens", 0) for run in rows)}
    return {"dedupRule": DEDUP_RULE, "budget": budget, "seeds": list(seeds), "seedCases": len(seedCases),
        "criterion": criterion.model_dump(mode="json"), "runs": runs, "summary": summary,
        "note": "Out-of-fold development evidence. Adaptively selected findings are exploratory and need separate validation."}
