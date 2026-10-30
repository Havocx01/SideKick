"""Run the full synthetic investigation: discover, reproduce, reduce, compare a remedy and export public evidence.

Uses a deliberately fragile 0.95 warning threshold on synthetic data so failures exist to investigate.
No provider calls are made. The investigation appears in the local workbench under Investigations.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import EXPERIMENT, Settings  # noqa: E402
from app.data.synthetic import make_synthetic_dataset  # noqa: E402
from app.faults.evaluator import FixedDevelopmentEvaluator  # noqa: E402
from app.faults.profiles import loadPolicy  # noqa: E402
from app.faults.replay import export_evaluation  # noqa: E402
from app.faults.scenarios import FaultCase  # noqa: E402
from app.investigator.findings import FindingCriterion  # noqa: E402
from app.investigator.publication import publicExport  # noqa: E402
from app.investigator.schemas import InvestigationCreate, ReduceRequest, RemedyRequest, StartRequest  # noqa: E402
from app.investigator.service import InvestigationService  # noqa: E402
from app.models.candidates import LogisticRegressionCandidate  # noqa: E402
from app.models.train import train_development  # noqa: E402

CANDIDATE = "logistic_regression/lr-probe"
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
    engine = FixedDevelopmentEvaluator(training, {CANDIDATE: .95}, loadPolicy("synthetic-rotating-v1", max_evaluations=128))
    export_evaluation(engine, engine.evaluate(FaultCase.model_validate(CASES[0])), path)
    return path


def describe(case):
    return " + ".join(f"{atom['sensor']} {atom['kind']} from {atom['onset_before_failure']} cycles before failure" for atom in case["components"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT / "artifacts" / "investigations", help="Investigation registry and store.")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "demo-public-evidence.json")
    args = parser.parse_args(argv)

    name = "demo-fragile-threshold"
    context(args.root, name)
    service = InvestigationService(args.root, Settings(mode="full"))
    try:
        investigation = service.create("local", InvestigationCreate(context=name, seed=3, proposals=CASES, maxExperiments=12,
            objective="Demo: find sensor faults that cost useful warnings at a fragile threshold.", criterion=FindingCriterion(candidate=CANDIDATE)))

        def step(submit, request):
            submit("local", investigation, request)
            service.wait(investigation, timeout=600)
            return service.view("local", investigation)

        view = step(lambda owner, id, request: service.start(owner, id, request, lambda: False), StartRequest(requestId=f"demo-run-{investigation[:8]}"))
        failure = next((item for item in view.findings if item.is_discovery), None)
        print(f"Investigation {investigation}: {view.experimentsUsed} experiments, findings {[item.status for item in view.findings if item.attempt_id]}")
        if failure is None:
            print("No measured failure under the criterion; nothing to reduce.")
        else:
            print(f"Measured failure: {failure.family}, useful warnings {failure.clean_detection:.0%} -> {failure.faulted_detection:.0%}")
            print(f"Replay matches: {service.replay('local', investigation, failure.attempt_id)['matches']}")
            view = step(service.reduce, ReduceRequest(requestId=f"demo-reduce-{investigation[:8]}", attempt=failure.attempt_id, maxExperiments=24))
            reduction = view.reductions[-1]
            print(f"Reduced ({reduction['status']}): {describe(reduction['final'])}")
            for claim in reduction["claims"]:
                print(f"  {claim}")
            view = step(service.remedy, RemedyRequest(requestId=f"demo-remedy-{investigation[:8]}", kind="threshold", threshold=.5))
            remedy = view.remedies[-1]
            print(f"Remedy threshold 0.5: improved {remedy['improved']}, degraded {remedy['degraded']}, meets criteria {remedy['meetsCriteria']}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(publicExport(service.store, investigation, contextName=name), indent=2) + "\n", encoding="utf-8")
        print(f"Public evidence: {args.output}")
        print("Open Sidekick in full mode and choose Investigations to inspect it.")
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
