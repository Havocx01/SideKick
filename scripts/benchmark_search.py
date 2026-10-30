"""Compare search strategies under one budget and one discovery criterion.

By default every strategy runs on the synthetic fixture. With --recorded, the strategies run on that live investigation's own
context, criterion, experiment allowance and supplied cases, and the recorded Nemotron run is reported as it happened.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import EXPERIMENT  # noqa: E402
from app.data.synthetic import make_synthetic_dataset  # noqa: E402
from app.faults.evaluator import FixedDevelopmentEvaluator  # noqa: E402
from app.faults.profiles import loadPolicy  # noqa: E402
from app.faults.investigation import InvestigationStore  # noqa: E402
from app.faults.replay import load_trusted_context  # noqa: E402
from app.investigator.benchmark import STRATEGIES, benchmark, recordedRun, suppliedCases  # noqa: E402
from app.investigator.findings import FindingCriterion, loadCriterion  # noqa: E402
from app.investigator.search import seedSuite  # noqa: E402
from app.models.candidates import LogisticRegressionCandidate  # noqa: E402
from app.models.train import train_development  # noqa: E402

CANDIDATE = "logistic_regression/lr-probe"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Report JSON path.")
    parser.add_argument("--budget", type=int, default=24, help="Experiments per run, including seed cases.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--thresholds", type=float, nargs="+", default=[.95, .9], help="One fixed context per warning threshold.")
    parser.add_argument("--recorded", nargs=2, metavar=("STORE", "ID"), help="A saved Nemotron investigation to compare on its own terms.")
    parser.add_argument("--context", type=Path, help="With --recorded, the context package that investigation used.")
    parser.add_argument("--trust-local-artifact", action="store_true", help="Only for a package you produced and trust; joblib can execute code.")
    args = parser.parse_args(argv)
    if args.recorded:
        return compareRecorded(args)

    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5, horizon_cycles=20, min_useful_lead=5,
        late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
    training = train_development(dataset, config=config, candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300})])
    policy = loadPolicy("synthetic-rotating-v1", max_evaluations=128)
    contexts = {f"threshold-{value:g}": (lambda value=value: FixedDevelopmentEvaluator(training, {CANDIDATE: value}, policy)) for value in args.thresholds}
    report = benchmark(contexts, FindingCriterion(candidate=CANDIDATE), STRATEGIES, budget=args.budget, seeds=tuple(args.seeds),
        seedCases=seedSuite(policy, config, 3))
    return write(report, args.output)


def compareRecorded(args):
    if not args.context:
        raise SystemExit("--recorded needs --context with the package the investigation used")
    store, investigation = InvestigationStore(Path(args.recorded[0])), args.recorded[1]
    record, criterion = store.get(investigation), loadCriterion(store, investigation)
    if criterion is None:
        raise SystemExit("The recorded investigation has no saved finding criterion")
    load = lambda: load_trusted_context(args.context, trusted=args.trust_local_artifact)  # noqa: E731
    record.check_context(load())
    report = benchmark({"recorded-context": load}, criterion, STRATEGIES, budget=store.load(investigation).budget.max_experiments,
        seeds=tuple(args.seeds), seedCases=suppliedCases(store, investigation), recorded={"recorded-context": recordedRun(store, investigation, criterion)})
    report["recorded"] = {"investigation": investigation, "contextFingerprint": record.context_fingerprint, "policyFingerprint": record.policy.fingerprint}
    return write(report, args.output)


def write(report, output):
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, row in report["summary"].items():
        print(f"{name:9} families={row['uniqueDiscoveryFamilies']} runsWithDiscovery={row['runsWithDiscovery']}/{row['runs']} "
            f"firstDiscovery={row['meanFirstDiscovery']} strongestDrop={row['meanStrongestDrop']} duplicates={row['duplicates']} providerCalls={row['providerCalls']} invalidReplies={row['invalidReplies']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
