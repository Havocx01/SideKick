"""Compare search strategies on the synthetic fixture under one budget and one discovery criterion."""
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
from app.investigator.benchmark import STRATEGIES, benchmark, recordedStrategy  # noqa: E402
from app.investigator.findings import FindingCriterion  # noqa: E402
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
    parser.add_argument("--recorded", type=Path, help="JSON list of cases a controller proposed, run as one more strategy.")
    parser.add_argument("--provider-calls", type=int, default=0, help="Provider calls the recorded proposals cost.")
    args = parser.parse_args(argv)

    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5, horizon_cycles=20, min_useful_lead=5,
        late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
    training = train_development(dataset, config=config, candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300})])
    policy = loadPolicy("synthetic-rotating-v1", max_evaluations=128)
    contexts = {f"threshold-{value:g}": (lambda value=value: FixedDevelopmentEvaluator(training, {CANDIDATE: value}, policy)) for value in args.thresholds}
    strategies = dict(STRATEGIES)
    if args.recorded:
        strategies["recorded"] = recordedStrategy(json.loads(args.recorded.read_text(encoding="utf-8")), args.provider_calls)

    report = benchmark(contexts, FindingCriterion(candidate=CANDIDATE), strategies, budget=args.budget, seeds=tuple(args.seeds),
        seedCases=seedSuite(policy, config, 3))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, row in report["summary"].items():
        print(f"{name:9} families={row['uniqueDiscoveryFamilies']} runsWithDiscovery={row['runsWithDiscovery']}/{row['runs']} "
            f"firstDiscovery={row['meanFirstDiscovery']} strongestDrop={row['meanStrongestDrop']} duplicates={row['duplicates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
