"""Train an isolated synthetic fixture once, evaluate a compound case, or replay a trusted package."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import EXPERIMENT
from app.data.synthetic import make_synthetic_dataset
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.profiles import loadPolicy
from app.faults.replay import export_evaluation, replay_evaluation
from app.faults.scenarios import FaultCase, FaultPolicy
from app.models.candidates import AgeBaselineCandidate, LogisticRegressionCandidate
from app.models.train import train_development
from app.scoring.pipeline import pick_thresholds
from app.scoring.selection import default_criteria


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="Create a new directory for the synthetic local evaluation.")
    mode.add_argument("--replay", type=Path, help="Reproduce a previously exported local evaluation without fitting.")
    parser.add_argument("--trust-local-artifact", action="store_true", help="Only for a package you produced and trust; joblib can execute code.")
    parser.add_argument("--scenario", type=Path, help="Optional bounded FaultCase JSON for the synthetic fixture.")
    parser.add_argument("--profile", help="Fault profile to constrain scenarios, e.g. synthetic-rotating-v1.")
    args = parser.parse_args(argv)
    if args.replay:
        if args.scenario:
            parser.error("Replay uses its recorded scenario; --scenario is only for new evaluations")
        result = replay_evaluation(args.replay, trusted=args.trust_local_artifact)
    else:
        if args.output.exists():
            parser.error("Choose a new output directory; existing runs are never overwritten")
        if args.scenario and args.scenario.stat().st_size > 65536:
            parser.error("Scenario JSON exceeds its size limit")
        case = FaultCase.model_validate(json.loads(args.scenario.read_text(encoding="utf-8"))) if args.scenario else FaultCase(components=[
            {"sensor": "temp_bearing", "kind": "dropout", "duration": "persistent", "onset_before_failure": 40},
            {"sensor": "vibration_rms", "kind": "drift", "duration": "persistent", "onset_before_failure": 40,
                "severity_sd": 1.5, "sign": 1, "ramp_cycles": 10}])
        config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5,
            horizon_cycles=20, min_useful_lead=5, late_window_end=4, transition_band_end=30, configs_per_candidate=1)
        dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
        policy = loadPolicy(args.profile) if args.profile else FaultPolicy(allowed_sensors=tuple(dataset.sensors))
        policy.check(case, config)
        training = train_development(dataset, config=config,
            candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300}), AgeBaselineCandidate("age-probe")])
        choices = pick_thresholds(training, default_criteria(config), config=config)
        evaluator = FixedDevelopmentEvaluator(training, {name: choice.threshold for name, choice in choices.items()}, policy)
        result = evaluator.evaluate(case)
        export_evaluation(evaluator, result, args.output)
    print(json.dumps({"mode": "replay" if args.replay else "synthetic_evaluation", "scenario_id": result.scenario_id,
        "status": result.status, "expected_histories": result.expected_histories, "evaluated_histories": result.evaluated_histories,
        "context_fingerprint": result.context_fingerprint, "provider_requests": 0,
        "note": "Synthetic development evidence only; no reserved histories scored and no field benefit established."}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
