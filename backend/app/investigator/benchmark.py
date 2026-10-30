"""Strategy-neutral search benchmark on one fixed development context."""
import json
import time

import numpy as np

from app.faults.scenarios import FaultCase
from app.investigator.findings import classify, family
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


def recordedStrategy(cases, providerCalls=0):
    def factory(policy, config, rng):
        queue = list(cases)
        propose = lambda history: queue.pop(0) if queue else None  # noqa: E731
        propose.providerCalls = providerCalls
        return propose
    return factory


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
        drop = finding.clean_detection - finding.faulted_detection if finding.faulted_detection is not None else None
        lost = sum(len(effect.histories) for effect in finding.effects if effect.kind != "alarm_burden")
        history.append({"experiment": len(history) + 1, "case": case.model_dump(mode="json"), "family": family(case),
            "status": finding.status, "drop": drop, "lost": lost, "coverage": finding.coverage})

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
        "elapsedSeconds": round(time.monotonic() - started, 3), "providerCalls": getattr(propose, "providerCalls", 0)}


def benchmark(contexts, criterion, strategies, *, budget=16, seeds=(0, 1, 2), seedCases=()) -> dict:
    """contexts maps a label to a factory returning a fresh evaluator, so no strategy reuses another's cache."""
    runs = []
    for label, makeEvaluator in contexts.items():
        for name, factory in strategies.items():
            for seed in seeds:
                evaluator = makeEvaluator()
                propose = factory(evaluator.policy, evaluator.config, np.random.default_rng(seed))
                runs.append({"context": label, "strategy": name, "seed": seed,
                    **runStrategy(evaluator, criterion, propose, budget, seedCases)})

    summary = {}
    for name in strategies:
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
            "providerCalls": sum(run["providerCalls"] for run in rows)}
    return {"dedupRule": DEDUP_RULE, "budget": budget, "seeds": list(seeds), "seedCases": len(seedCases),
        "criterion": criterion.model_dump(mode="json"), "runs": runs, "summary": summary,
        "note": "Out-of-fold development evidence. Adaptively selected findings are exploratory and need separate validation."}
