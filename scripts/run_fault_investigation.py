"""Create, run, inspect or cancel a saved fault investigation against a trusted Phase 2 context package."""
import argparse
import json
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore  # noqa: E402
from app.faults.replay import load_trusted_context  # noqa: E402

MAX_PROPOSAL_FILE_BYTES = 4 * 1024 * 1024


def read_proposals(path: Path):
    if path.stat().st_size > MAX_PROPOSAL_FILE_BYTES:
        raise SystemExit("Proposal file exceeds its size limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Proposal file must contain a JSON list of scenarios")
    return data


def context(args):
    if not args.context:
        raise SystemExit("--context is required to create or run an investigation")
    return load_trusted_context(args.context, trusted=args.trust_local_artifact)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True, help="Directory holding investigations.sqlite3.")
    parser.add_argument("--context", type=Path, help="Phase 2 export package providing the fixed fitted context.")
    parser.add_argument("--trust-local-artifact", action="store_true", help="Only for a package you produced and trust; joblib can execute code.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--create", type=Path, metavar="PROPOSALS_JSON", help="Create an investigation from a JSON list of scenarios.")
    action.add_argument("--add", nargs=2, metavar=("ID", "PROPOSALS_JSON"), help="Append proposals to an investigation.")
    action.add_argument("--run", metavar="ID", help="Run pending proposals within the saved budget.")
    action.add_argument("--status", metavar="ID", help="Show saved state without loading a model context.")
    action.add_argument("--cancel", metavar="ID", help="Ask an active or future run to stop.")
    action.add_argument("--resume", metavar="ID", help="Clear a cancellation so the investigation can run again.")
    parser.add_argument("--max-experiments", type=int, default=16)
    parser.add_argument("--max-failures", type=int, default=3)
    parser.add_argument("--max-attempts-per-scenario", type=int, default=2)
    parser.add_argument("--max-run-seconds", type=float, default=600)
    args = parser.parse_args(argv)
    store = InvestigationStore(args.store)

    if args.create:
        budget = InvestigationBudget(max_experiments=args.max_experiments, max_failures=args.max_failures,
            max_attempts_per_scenario=args.max_attempts_per_scenario, max_run_seconds=args.max_run_seconds)
        investigation = store.create(context(args), budget, read_proposals(args.create))
        output = {"investigation_id": investigation, "proposals": len(store.load(investigation).proposals)}
    elif args.add:
        output = {"investigation_id": args.add[0], "added": store.add_proposals(args.add[0], read_proposals(Path(args.add[1])))}
    elif args.run:
        runner = ExperimentRunner(store, context(args))
        interrupted = {"flag": False}

        def stop(*_):
            interrupted["flag"] = True  # Cooperative: the current experiment stops at its next check.
        signal.signal(signal.SIGINT, stop)
        output = runner.run(args.run, cancelled=lambda: interrupted["flag"]).model_dump(mode="json")
        output["provider_requests"] = 0
    elif args.status:
        state = store.load(args.status)
        output = state.model_dump(mode="json")
    elif args.cancel:
        store.request_cancel(args.cancel)
        output = {"investigation_id": args.cancel, "cancel_requested": True}
    else:
        store.resume(args.resume)
        output = {"investigation_id": args.resume, "cancel_requested": False}
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
