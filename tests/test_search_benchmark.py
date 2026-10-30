import importlib.util
import json
from pathlib import Path

import numpy as np

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.faults.replay import export_evaluation
from app.faults.scenarios import FaultCase
from app.investigator.benchmark import DEDUP_RULE, STRATEGIES, benchmark, climbStrategy, recordedRun, suppliedCases
from app.investigator.findings import FindingCriterion, classify, saveCriterion
from app.investigator.search import fixedSuite, neighbor, randomCase, seedSuite
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
POLICY = loadPolicy("synthetic-rotating-v1", max_evaluations=128)
SUPPLIED = {"components": [component("temp_bearing", kind="stuck", onset_before_failure=60)]}
STUCK_PAIR = {"components": [component("vibration_rms", kind="stuck", onset_before_failure=60), component("oil_particles", kind="stuck", onset_before_failure=60)]}


def contexts(fitted, built=None):
    def make(threshold):
        def factory():
            if built is not None:
                built.append(threshold)
            return FixedDevelopmentEvaluator(fitted, {LR: threshold}, POLICY)
        return factory
    return {"lr-0.95": make(.95), "lr-0.9": make(.9)}


def withoutTiming(report):
    return [{key: value for key, value in run.items() if key != "elapsedSeconds"} for run in report["runs"]]


def test_every_strategy_gets_the_same_budget_evidence_and_fresh_context(fitted):
    built = []
    seeds = seedSuite(POLICY, fitted.config, 3)
    report = benchmark(contexts(fitted, built), FindingCriterion(candidate=LR), STRATEGIES, budget=10, seeds=(0, 1), seedCases=seeds)
    assert len(report["runs"]) == len(built) == 2 * 3 * 2
    assert report["dedupRule"] == DEDUP_RULE and report["seedCases"] == 3 and "exploratory" in report["note"]
    for run in report["runs"]:
        assert run["experiments"] <= 10 and run["feasibleRate"] == 1.0 and run["errors"] == 0
        assert run["proposals"] == run["experiments"] + run["infeasible"] + run["duplicates"] + run["errors"]
    fixed = [run for run in report["runs"] if run["strategy"] == "fixed"]
    assert all(run["duplicates"] <= 3 for run in fixed)
    perContext = {}
    for run in fixed:
        perContext.setdefault(run["context"], []).append({key: value for key, value in run.items() if key not in {"seed", "elapsedSeconds"}})
    assert all(rows[0] == rows[1] for rows in perContext.values())
    assert set(report["summary"]) == {"fixed", "random", "climb"}
    json.dumps(report)


def test_benchmark_is_reproducible_for_the_same_seeds(fitted):
    first = benchmark(contexts(fitted), FindingCriterion(candidate=LR), STRATEGIES, budget=8, seeds=(3,))
    second = benchmark(contexts(fitted), FindingCriterion(candidate=LR), STRATEGIES, budget=8, seeds=(3,))
    assert withoutTiming(first) == withoutTiming(second)


def recordedInvestigation(fitted, tmp_path, monkeypatch):
    from test_nemotron_controller import proposal, provider, run, setup, stop
    fixed, store, investigation, config = setup(fitted, tmp_path, experiments=4)
    saveCriterion(store, investigation, FindingCriterion(candidate=LR))
    store.add_proposals(investigation, [SUPPLIED])
    provider(monkeypatch, [proposal("channel-99"), proposal("channel-1"), proposal("channel-1"), stop()])
    run(store, fixed, config, investigation)
    return fixed, store, investigation


def test_a_recorded_nemotron_run_counts_rejected_duplicate_and_provider_work(fitted, tmp_path, monkeypatch):
    fixed, store, investigation = recordedInvestigation(fitted, tmp_path, monkeypatch)
    run = recordedRun(store, investigation, FindingCriterion(candidate=LR))
    assert (run["proposals"], run["experiments"], run["duplicates"], run["infeasible"], run["errors"]) == (4, 2, 1, 1, 0)
    assert run["feasibleRate"] == .75 and run["providerCalls"] == 4 and run["invalidReplies"] == 1 and run["reductionExperiments"] == 0
    assert run["reservedCompletionTokens"] == 4 * 1024 and run["reportedCompletionTokens"] == 160 and run["prompt"].startswith("nemotron-fault-search")
    assert [FaultCase.model_validate(item).scenario_id for item in suppliedCases(store, investigation)] == [FaultCase.model_validate(SUPPLIED).scenario_id]
    measured = [store.result(item.id) for item in store.load(investigation).attempts]
    expected = [classify(result, FindingCriterion(candidate=LR)) for result in measured]
    assert run["discoveries"] == sum(item.is_discovery for item in expected) and run["familiesTested"] == 2
    assert run["strongestDrop"] == max(item.clean_detection - item.faulted_detection for item in expected)


def test_benchmark_cli_compares_a_recorded_run_on_its_own_context_and_allowance(fitted, tmp_path, monkeypatch, capsys):
    fixed, store, investigation = recordedInvestigation(fitted, tmp_path, monkeypatch)
    export_evaluation(fixed, fixed.evaluate(FaultCase.model_validate(SUPPLIED)), tmp_path / "context")
    output = tmp_path / "report.json"
    assert cli().main(["--output", str(output), "--seeds", "0", "1", "--recorded", str(tmp_path / "store"), investigation,
        "--context", str(tmp_path / "context"), "--trust-local-artifact"]) == 0
    report = json.loads(output.read_text())
    assert report["budget"] == 4 and report["seedCases"] == 1 and report["recorded"]["investigation"] == investigation
    assert set(report["summary"]) == {"nemotron", "fixed", "random", "climb"} and report["summary"]["nemotron"]["runs"] == 1
    assert all(run["context"] == "recorded-context" and run["experiments"] <= 4 for run in report["runs"])
    assert "invalidReplies=1" in capsys.readouterr().out


def test_generators_stay_inside_the_profile(fitted):
    rng = np.random.default_rng(1)
    for _ in range(200):
        POLICY.check(FaultCase.model_validate(randomCase(POLICY, fitted.config, rng)), fitted.config)
    suite = fixedSuite(POLICY, fitted.config)
    assert len(suite) == sum(len(rule.kinds) for rule in POLICY.profile.sensors)
    for case in suite:
        POLICY.check(FaultCase.model_validate(case), fitted.config)
    valid = 0
    for _ in range(200):
        try:
            POLICY.check(FaultCase.model_validate(neighbor(STUCK_PAIR, POLICY, fitted.config, rng)), fitted.config)
            valid += 1
        except ValueError:
            pass
    assert valid == 200


def test_climber_refines_the_best_measured_case_without_repeating_it(fitted):
    propose = climbStrategy(POLICY, fitted.config, np.random.default_rng(5))
    best = FaultCase.model_validate(STUCK_PAIR).model_dump(mode="json")
    history = [{"experiment": 1, "case": best, "drop": .27, "lost": 6}, {"experiment": 2, "case": randomCase(POLICY, fitted.config, np.random.default_rng(9)), "drop": 0.0, "lost": 0}]
    proposals = [FaultCase.model_validate(propose(history)) for _ in range(30)]
    assert all(case.model_dump(mode="json") != best for case in proposals)
    near = [case for case in proposals if {atom.sensor for atom in case.components} & {"vibration_rms", "oil_particles"}]
    assert len(near) >= 20


def cli():
    spec = importlib.util.spec_from_file_location("benchmark_cli", Path(__file__).resolve().parents[1] / "scripts/benchmark_search.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_cli_writes_a_report_on_the_synthetic_fixture(tmp_path, capsys):
    output = tmp_path / "report.json"
    assert cli().main(["--output", str(output), "--budget", "6", "--seeds", "0"]) == 0
    report = json.loads(output.read_text())
    assert set(report["summary"]) == {"fixed", "random", "climb"} and report["budget"] == 6
    assert "climb" in capsys.readouterr().out
