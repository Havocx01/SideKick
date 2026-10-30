"""Train an isolated synthetic fixture once, evaluate a compound case, or replay a trusted package."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.faults.preparation import prepareSynthetic
from app.faults.replay import replay_evaluation
from app.faults.scenarios import FaultCase


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
        case = FaultCase.model_validate(json.loads(args.scenario.read_text(encoding="utf-8"))) if args.scenario else None
        result = prepareSynthetic(args.output, profile=args.profile, case=case)
    print(json.dumps({"mode": "replay" if args.replay else "synthetic_evaluation", "scenario_id": result.scenario_id,
        "status": result.status, "expected_histories": result.expected_histories, "evaluated_histories": result.evaluated_histories,
        "context_fingerprint": result.context_fingerprint, "provider_requests": 0,
        "note": "Synthetic development evidence only; no reserved histories scored and no field benefit established."}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
