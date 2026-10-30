"""Run the full synthetic investigation: discover, reproduce, reduce, compare a remedy and export public evidence.

Uses a deliberately fragile 0.95 warning threshold on synthetic data so failures exist to investigate; it is a demonstration
setting, not a recommended one. Without --allow-nebius no provider calls are made and every case is hand-authored or seeded.
With it, Nemotron proposes further cases within the stated allowance, and the story reduces a Nemotron-chosen failure when one exists.
The investigation appears in the local workbench under Investigations.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import EXPERIMENT, Settings, get_settings  # noqa: E402
from app.experiments.provenance import source_digest  # noqa: E402
from app.data.synthetic import make_synthetic_dataset  # noqa: E402
from app.faults.evaluator import FixedDevelopmentEvaluator  # noqa: E402
from app.faults.profiles import loadPolicy  # noqa: E402
from app.faults.replay import export_evaluation  # noqa: E402
from app.faults.scenarios import FaultCase  # noqa: E402
from app.investigator.controller import controllerStatus  # noqa: E402
from app.investigator.findings import FindingCriterion  # noqa: E402
from app.investigator.publication import publicExport  # noqa: E402
from app.investigator.reduction import regressionCase  # noqa: E402
from app.investigator.validation import assess, freeze, freshSynthetic  # noqa: E402
from app.investigator.schemas import InvestigationCreate, ReduceRequest, RemedyRequest, StartRequest  # noqa: E402
from app.investigator.service import InvestigationService  # noqa: E402
from app.models.candidates import LogisticRegressionCandidate  # noqa: E402
from app.models.train import train_development  # noqa: E402

CANDIDATE = "logistic_regression/lr-probe"
THRESHOLD = .95
DEMONSTRATION = {"threshold": THRESHOLD, "note": "Demonstration setting: this warning threshold is deliberately fragile so that faults cost warnings. "
    "Do not read these findings as properties of a recommended model."}
CASES = [
    {"components": [{"sensor": "vibration_rms", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60},
        {"sensor": "oil_particles", "kind": "stuck", "duration": "persistent", "onset_before_failure": 60}]},
    {"components": [{"sensor": "pressure_out", "kind": "drift", "duration": "persistent", "onset_before_failure": 60, "severity_sd": 2.0, "sign": 1, "ramp_cycles": 10},
        {"sensor": "flow_rate", "kind": "dropout", "duration": "persistent", "onset_before_failure": 60}]},
]


def context(root: Path, name: str):
    path = root / "contexts" / name
    if (path / "manifest.json").is_file():
        return path
    config = replace(EXPERIMENT, holdout_engines=4, n_folds=2, feature_window=5, horizon_cycles=20, min_useful_lead=5,
        late_window_end=4, transition_band_end=30, configs_per_candidate=1)
    dataset = make_synthetic_dataset(n_equipment=26, min_life=85, max_life=100, config=config)
    training = train_development(dataset, config=config, candidates=[LogisticRegressionCandidate("lr-probe", {"max_iter": 300})])
    engine = FixedDevelopmentEvaluator(training, {CANDIDATE: THRESHOLD}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    export_evaluation(engine, engine.evaluate(FaultCase.model_validate(CASES[0])), path)
    return path


def describe(case):
    return " + ".join(f"{atom['sensor']} {atom['kind']} from {atom['onset_before_failure']} cycles before failure" for atom in case["components"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts" / "investigations", help="Investigation registry and store.")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "demo-public-evidence.json")
    parser.add_argument("--fresh-seed", type=int, help="Seed for the fresh synthetic histories used once for validation; defaults to one per investigation.")
    parser.add_argument("--allow-nebius", action="store_true", help="Also let Nemotron propose cases; sends the objective and aggregate results to Nebius.")
    parser.add_argument("--max-provider-calls", type=int, default=4)
    parser.add_argument("--max-completion-tokens", type=int, default=16384)
    args = parser.parse_args(argv)

    # Contexts are bound to the source that built them, so each source gets its own.
    name = f"demo-fragile-threshold-{source_digest()[:8]}"
    context(args.root, name)
    if args.allow_nebius:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    service = InvestigationService(args.root, get_settings() if args.allow_nebius else Settings(mode="full"))
    try:
        investigation = service.create("local", InvestigationCreate(context=name, seed=3, proposals=CASES, maxExperiments=12,
            objective="Demo: find sensor faults that cost useful warnings at a fragile threshold.", criterion=FindingCriterion(candidate=CANDIDATE)))

        def step(submit, request):
            submit("local", investigation, request)
            service.wait(investigation, timeout=600)
            return service.view("local", investigation)

        view = step(lambda owner, id, request: service.start(owner, id, request, lambda: False), StartRequest(requestId=f"demo-run-{investigation[:8]}"))
        if args.allow_nebius:
            view = step(lambda owner, id, request: service.start(owner, id, request, lambda: True), StartRequest(requestId=f"demo-agent-{investigation[:8]}",
                mode="agent", allowProvider=True, maxProviderCalls=args.max_provider_calls, maxCompletionTokens=args.max_completion_tokens))
            controller = controllerStatus(service.store, investigation)
            print(f"Nemotron: {controller['callsUsed']} calls, stop {controller['stopReason']}, {controller['reportedCompletionTokens']} reported completion tokens")
        chosen = {call["proposalId"] for call in (controllerStatus(service.store, investigation) or {"calls": []})["calls"] if call["proposalId"]}
        proposalOf = {item.id: item.proposal_id for item in service.store.load(investigation).attempts}
        origin = lambda finding: "Nemotron" if proposalOf.get(finding.attempt_id) in chosen else "hand-authored or seeded"  # noqa: E731
        print(f"Demonstration setting: warning threshold {THRESHOLD} is deliberately fragile.")
        print(f"Investigation {investigation}: {view.experimentsUsed} experiments")
        for item in view.findings:
            if item.attempt_id:
                print(f"  {item.status:20} {item.family}  chosen by {origin(item)}")
        discoveries = [item for item in view.findings if item.is_discovery]
        failure = next((item for item in discoveries if origin(item) == "Nemotron"), discoveries[0] if discoveries else None)
        if failure is None:
            print("No measured failure under the criterion; nothing to reduce.")
        else:
            print(f"Measured failure ({origin(failure)}): {failure.family}, useful warnings {failure.clean_detection:.0%} -> {failure.faulted_detection:.0%}")
            print(f"Replay matches: {service.replay('local', investigation, failure.attempt_id)['matches']}")
            view = step(service.reduce, ReduceRequest(requestId=f"demo-reduce-{investigation[:8]}", attempt=failure.attempt_id, maxExperiments=24))
            reduction = view.reductions[-1]
            print(f"Reduced ({reduction['status']}): {describe(reduction['final'])}")
            for claim in reduction["claims"]:
                print(f"  {claim}")
            regression = args.output.with_name(f"{args.output.stem}-regression.json")
            regression.parent.mkdir(parents=True, exist_ok=True)
            regression.write_text(json.dumps(regressionCase(service.store, reduction["id"]), indent=2) + "\n", encoding="utf-8")
            print(f"Regression case: {regression}")
            view = step(service.remedy, RemedyRequest(requestId=f"demo-remedy-{investigation[:8]}", kind="threshold", threshold=.5))
            remedy = view.remedies[-1]
            clean = remedy["clean"]
            print(f"Remedy threshold 0.5: improved {remedy['improved']}, degraded {remedy['degraded']}, still failing {remedy['stillFailing']}, "
                f"meets criteria {remedy['meetsCriteria']}")
            print(f"  Development clean histories: useful warnings {clean['original']['detection']:.0%} -> {clean['remedy']['detection']:.0%}, alarm burden "
                f"{clean['original']['alarmBurden']:.3f} -> {clean['remedy']['alarmBurden']:.3f}, median lead {clean['original']['medianLead']} -> "
                f"{clean['remedy']['medianLead']} cycles; {sum(row['remedy']['exclusions'] for row in remedy['cases'])} exclusions; "
                f"{remedy['cost']['prepareSeconds'] + remedy['cost']['evaluateSeconds']:.1f}s")
            frozen = freeze(service.store, investigation, remedyThreshold=.5)
            engine = service.evaluator(name)
            report = assess(service.store, frozen["id"], engine, freshSynthetic(engine.config, args.fresh_seed if args.fresh_seed is not None else int(investigation[:6], 16)))
            print(f"Frozen procedure {frozen['procedureDigest'][:12]}, assessed once on {report['freshHistories']} fresh synthetic histories:")
            for row in report["cases"]:
                print(f"  {row['label']}: {row['original']['status']} (remedy: {row['remedy']['status']})")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(publicExport(service.store, investigation, contextName=name, demonstration=DEMONSTRATION), indent=2) + "\n", encoding="utf-8")
        print(f"Public evidence: {args.output}")
        print("Open Sidekick in full mode and choose Investigations to inspect it.")
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
