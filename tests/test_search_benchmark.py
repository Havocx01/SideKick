import json

import numpy as np

from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.faults.scenarios import FaultCase
from app.investigator.benchmark import DEDUP_RULE, STRATEGIES, benchmark, climbStrategy, recordedStrategy, runStrategy
from app.investigator.findings import FindingCriterion
from app.investigator.search import fixedSuite, neighbor, randomCase, seedSuite
from test_compound_faults import component, fitted as fitted  # noqa: F401

LR = "logistic_regression/lr-probe"
POLICY = loadPolicy("synthetic-rotating-v1", max_evaluations=128)
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


def test_rejected_duplicate_and_provider_work_is_counted_not_hidden(fitted):
    cases = [{"components": [component("temp_bearing")]}, {"components": [component("temp_bearing")]},
        {"components": [component("rated_voltage")]}, {"scenario": STUCK_PAIR, "reason": "recorded controller proposal"}]
    engine = FixedDevelopmentEvaluator(fitted, {LR: .95}, POLICY)
    propose = recordedStrategy(cases, providerCalls=4)(POLICY, engine.config, np.random.default_rng(0))
    run = runStrategy(engine, FindingCriterion(candidate=LR), propose, budget=8)
    assert (run["proposals"], run["experiments"], run["duplicates"], run["infeasible"]) == (4, 2, 1, 1)
    assert run["feasibleRate"] == .75 and run["providerCalls"] == 4
    assert run["firstDiscovery"] == 2 and run["discoveryFamilies"] == ["oil_particles:stuck+vibration_rms:stuck"]
    result = engine.evaluate(FaultCase.model_validate(STUCK_PAIR)).models[0]
    lost = sum(pair.clean.detected and not pair.faulted.detected for pair in result.pairs)
    assert run["mostLostWarnings"] == lost and lost > 0
    assert run["strongestDrop"] == lost / len(result.pairs)


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


def test_benchmark_cli_writes_a_report(tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("benchmark_cli", Path(__file__).resolve().parents[1] / "scripts/benchmark_search.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    recorded = tmp_path / "recorded.json"
    recorded.write_text(json.dumps([STUCK_PAIR]))
    output = tmp_path / "report.json"
    assert cli.main(["--output", str(output), "--budget", "6", "--seeds", "0", "--recorded", str(recorded)]) == 0
    report = json.loads(output.read_text())
    assert set(report["summary"]) == {"fixed", "random", "climb", "recorded"} and report["budget"] == 6
    assert "recorded" in capsys.readouterr().out
