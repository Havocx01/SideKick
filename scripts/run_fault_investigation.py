"""Create, run, inspect or cancel a saved fault investigation against a trusted Phase 2 context package."""
import argparse
import asyncio
import json
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.faults.investigation import ExperimentRunner, InvestigationBudget, InvestigationStore  # noqa: E402
from app.faults.replay import load_trusted_context  # noqa: E402
from app.investigator.findings import FindingCriterion, recordFindings, saveCriterion, summarize  # noqa: E402

MAX_PROPOSAL_FILE_BYTES = 4 * 1024 * 1024


def read_proposals(path: Path):
    if path.stat().st_size > MAX_PROPOSAL_FILE_BYTES:
        raise SystemExit("Proposal file exceeds its size limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Proposal file must contain a JSON list of scenarios")
    return data


def readCriterion(path: Path) -> FindingCriterion:
    if path.stat().st_size > 16384:
        raise SystemExit("Criterion file exceeds its size limit")
    return FindingCriterion.model_validate_json(path.read_text(encoding="utf-8"))


def context(args):
    if not args.context:
        raise SystemExit("--context is required to create or run an investigation")
    return load_trusted_context(args.context, trusted=args.trust_local_artifact)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True, help="Directory holding investigator.sqlite3.")
    parser.add_argument("--context", type=Path, help="Phase 2 export package providing the fixed fitted context.")
    parser.add_argument("--trust-local-artifact", action="store_true", help="Only for a package you produced and trust; joblib can execute code.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--create", type=Path, metavar="PROPOSALS_JSON", help="Create an investigation from a JSON list of scenarios.")
    action.add_argument("--attach", metavar="ID", help="Enable the runner for an existing investigation record.")
    action.add_argument("--add", nargs=2, metavar=("ID", "PROPOSALS_JSON"), help="Append proposals to an investigation.")
    action.add_argument("--run", metavar="ID", help="Run pending proposals within the saved budget.")
    action.add_argument("--agent", metavar="ID", help="Let Nemotron propose and run experiments within saved limits.")
    action.add_argument("--status", metavar="ID", help="Show saved state without loading a model context.")
    action.add_argument("--findings", metavar="ID", help="Classify recorded results with the saved criterion; no model context or provider call.")
    action.add_argument("--set-criterion", nargs=2, metavar=("ID", "CRITERION_JSON"), help="Save the finding criterion for an existing investigation.")
    action.add_argument("--cancel", metavar="ID", help="Ask an active or future run to stop.")
    action.add_argument("--resume", metavar="ID", help="Clear a cancellation so the investigation can run again.")
    parser.add_argument("--criterion", type=Path, metavar="CRITERION_JSON", help="Finding criterion to save with --create or --attach.")
    parser.add_argument("--max-experiments", type=int, default=16)
    parser.add_argument("--max-failures", type=int, default=3)
    parser.add_argument("--max-attempts-per-scenario", type=int, default=2)
    parser.add_argument("--max-run-seconds", type=float, default=600)
    parser.add_argument("--objective", default="Test supplied fault scenarios.", help="Objective for a new investigation.")
    parser.add_argument("--allow-nebius", action="store_true", help="Allow billable Nemotron calls with the objective, aliased policy and aggregate results.")
    parser.add_argument("--max-provider-calls", type=int, default=4)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--max-completion-tokens", type=int, default=32768)
    parser.add_argument("--max-input-bytes", type=int, default=32768)
    args = parser.parse_args(argv)
    if args.agent and not args.allow_nebius:
        parser.error("--agent requires --allow-nebius to send the objective and aggregate evidence to Nebius")
    store = InvestigationStore(args.store)

    if args.create:
        budget = InvestigationBudget(max_experiments=args.max_experiments, max_failures=args.max_failures,
            max_attempts_per_scenario=args.max_attempts_per_scenario, max_run_seconds=args.max_run_seconds)
        investigation = store.create(context(args), budget, read_proposals(args.create), objective=args.objective)
        output = {"investigation_id": investigation, "proposals": len(store.load(investigation).proposals)}
        if args.criterion:
            output["criterion"] = saveCriterion(store, investigation, readCriterion(args.criterion)).model_dump(mode="json")
    elif args.attach:
        output = {"investigation_id": store.attachRecord(args.attach)}
        if args.criterion:
            output["criterion"] = saveCriterion(store, args.attach, readCriterion(args.criterion)).model_dump(mode="json")
    elif args.add:
        output = {"investigation_id": args.add[0], "added": store.add_proposals(args.add[0], read_proposals(Path(args.add[1])))}
    elif args.run or args.agent:
        fixed = context(args)
        interrupted = {"flag": False}

        def stop(*_):
            interrupted["flag"] = True  # Cooperative: the current experiment stops at its next check.
        previous = signal.signal(signal.SIGINT, stop)
        try:
            if args.agent:
                from dotenv import load_dotenv
                from app.config import get_settings
                from app.investigator.controller import ControllerLimits, NemotronController
                load_dotenv(ROOT / ".env", override=False)
                limits = ControllerLimits(maxCalls=args.max_provider_calls, maxOutputTokens=args.max_output_tokens,
                    maxCompletionTokens=args.max_completion_tokens, maxInputBytes=args.max_input_bytes)
                controller = NemotronController(store, fixed, get_settings(), limits)
                output = asyncio.run(controller.run(args.agent, allowProvider=True, cancelled=lambda: interrupted["flag"]))
            else:
                output = ExperimentRunner(store, fixed).run(args.run, cancelled=lambda: interrupted["flag"]).model_dump(mode="json")
                output["provider_requests"] = 0
        finally:
            signal.signal(signal.SIGINT, previous)
    elif args.status:
        from app.investigator.controller import controllerStatus
        state = store.load(args.status)
        output = state.model_dump(mode="json")
        output["controller"] = controllerStatus(store, args.status)
    elif args.set_criterion:
        criterion = saveCriterion(store, args.set_criterion[0], readCriterion(Path(args.set_criterion[1])))
        output = {"investigation_id": args.set_criterion[0], "criterion": criterion.model_dump(mode="json")}
    elif args.findings:
        findings = recordFindings(store, args.findings)
        output = {"investigation_id": args.findings, **summarize(findings), "provider_requests": 0,
            "findings": [finding.model_dump(mode="json") for finding in findings]}
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
