"""Run the development evaluation and write the evidence bundle.

This is the local pipeline. It profiles the data, trains every candidate with
grouped cross-validation, freezes each candidate's alert threshold on clean
out-of-fold predictions, runs the fault matrix, applies the acceptance criteria,
records every result in the evidence store and writes the bundle the hosted demo
serves.

The held-out engines are not touched here. They are scored once, by
``scripts/final_evaluation.py``, after the configuration is frozen.

Examples
--------
    python scripts/run_pipeline.py                        # FD001, full matrix
    python scripts/run_pipeline.py --required-only        # selection set only
    python scripts/run_pipeline.py --fast                 # quick wiring check
    python scripts/run_pipeline.py --source synthetic     # no download needed
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import EXPERIMENT, get_settings  # noqa: E402
from app.data import load_dataset, make_synthetic_dataset  # noqa: E402
from app.evidence import EvidenceStore, build_bundle, mirror_run, write_bundle  # noqa: E402
from app.faults.matrix import describe_matrix  # noqa: E402
from app.schemas import AcceptanceCriteria  # noqa: E402
from app.scoring.pipeline import evaluate  # noqa: E402
from app.utils.logging_setup import get_logger  # noqa: E402

logger = get_logger("run_pipeline")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="cmapss", choices=["cmapss", "synthetic", "csv"])
    parser.add_argument("--subset", default="FD001")
    parser.add_argument("--path", type=Path, help="CSV path when --source csv")
    parser.add_argument("--engines", type=int, default=60, help="synthetic engine count")
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="run only the bounded selection set, skipping the wider reported matrix",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="reduced folds, one configuration per family, three sensors: wiring check only",
    )
    parser.add_argument("--sensors", help="comma-separated sensors to fault-test")
    parser.add_argument("--max-sensors", type=int, help="cap the fault-tested sensor count")
    parser.add_argument("--min-detection", type=float, help="override the required detection rate")
    parser.add_argument("--max-burden", type=float, help="override the permitted early alarm burden")
    parser.add_argument("--replay-engines", type=int, default=6)
    parser.add_argument("--bundle", type=Path, help="where to write the evidence bundle")
    parser.add_argument("--no-bundle", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()

    config = EXPERIMENT
    if args.fast:
        config = replace(
            config, holdout_engines=10, n_folds=3, configs_per_candidate=1
        )
    config.validate()

    if args.source == "synthetic":
        dataset = make_synthetic_dataset(n_equipment=args.engines, config=config)
    else:
        dataset = load_dataset(
            args.source, subset=args.subset, path=args.path, config=config
        )
    logger.info("%s", dataset.describe())
    logger.info("data hash %s, config fingerprint %s", dataset.data_hash, config.fingerprint())

    criteria: AcceptanceCriteria | None = None
    if args.min_detection is not None or args.max_burden is not None:
        criteria = AcceptanceCriteria(
            min_detection_fraction=(
                args.min_detection if args.min_detection is not None else config.min_detection_fraction
            ),
            max_early_alarm_burden=(
                args.max_burden if args.max_burden is not None else config.max_early_alarm_burden
            ),
            min_useful_lead=config.min_useful_lead,
            horizon_cycles=config.horizon_cycles,
        )

    fault_sensors: list[str] | None = None
    if args.sensors:
        fault_sensors = [s.strip() for s in args.sensors.split(",") if s.strip()]
    elif args.fast:
        from app.data.profiler import profile_dataset

        fault_sensors = profile_dataset(dataset, config=config).varying_sensors[:3]
    elif args.max_sensors:
        from app.data.profiler import profile_dataset

        fault_sensors = profile_dataset(dataset, config=config).varying_sensors[: args.max_sensors]

    if fault_sensors:
        logger.info("fault matrix over %d sensors: %s", len(fault_sensors), ", ".join(fault_sensors))
        logger.info("scenario counts: %s", describe_matrix(fault_sensors, config))

    store = EvidenceStore()
    parent = store.start_run(
        "training",
        config=config,
        data_hash=dataset.data_hash,
        params={
            "dataset_id": dataset.dataset_id,
            "source": dataset.source,
            "engines": len(dataset.equipment_ids),
            "rows": len(dataset.frame),
            "required_only": bool(args.required_only),
            "fast": bool(args.fast),
        },
    )

    result = evaluate(
        dataset,
        config=config,
        criteria=criteria,
        fault_sensors=fault_sensors,
        include_full_matrix=not args.required_only,
    )

    # One run record per candidate, so every reported metric has an owner.
    for candidate_name, candidate in result.training.specs.items():
        clean = result.clean[candidate_name]
        verdict = next(
            v
            for v in result.selection.ranked
            if v.candidate == candidate.kind and v.config_id == candidate.config_id
        )
        record = store.start_run(
            "fault_matrix",
            config=config,
            data_hash=dataset.data_hash,
            parent_run_id=parent.run_id,
            params={
                "candidate": candidate.kind.value,
                "config_id": candidate.config_id,
                **{f"param.{k}": v for k, v in candidate.params.items()},
                "threshold": result.thresholds[candidate_name],
            },
        )
        store.log_metrics(
            record,
            {
                "clean_detection_fraction": clean.detection_fraction,
                "clean_detection_ci_lower": clean.detection_ci.lower,
                "clean_detection_ci_upper": clean.detection_ci.upper,
                "clean_early_alarm_burden": clean.early_alarm_burden,
                "clean_late_engines": clean.late,
                "clean_missed_engines": clean.missed,
                "clean_median_lead_time": clean.median_lead_time or 0.0,
                "required_mean_detection": verdict.mean_detection_required,
                "required_worst_detection": verdict.worst_detection_required,
                "required_passed": verdict.required_passed,
                "required_scenarios": verdict.required_scenarios,
                "qualifies": float(verdict.qualifies),
            },
        )
        mirror_run(record)

    selection_run = store.start_run(
        "selection",
        config=config,
        data_hash=dataset.data_hash,
        parent_run_id=parent.run_id,
        params={
            "outcome": result.selection.outcome.value,
            "min_detection_fraction": result.criteria.min_detection_fraction,
            "max_early_alarm_burden": result.criteria.max_early_alarm_burden,
            "recommended": (
                f"{result.selection.recommended.candidate.value}/"
                f"{result.selection.recommended.config_id}"
                if result.selection.recommended
                else "none"
            ),
        },
        notes=result.selection.notes,
    )
    store.log_json_artifact(selection_run, "selection", result.selection.model_dump(mode="json"))
    mirror_run(selection_run)

    print_summary(result)

    if not args.no_bundle:
        runs = store.list_runs(limit=60)
        bundle = build_bundle(
            result, config=config, runs=runs, replay_engines=args.replay_engines
        )
        write_bundle(bundle, args.bundle)

    return 0


def print_summary(result) -> None:
    selection = result.selection
    print()
    print("=" * 96)
    print(f"outcome: {selection.outcome.value}")
    print(
        f"criteria: detection >= {selection.criteria.min_detection_fraction:.0%}, "
        f"early alarm burden <= {selection.criteria.max_early_alarm_burden:.1%}, "
        f"useful window {selection.criteria.horizon_cycles}-{selection.criteria.min_useful_lead} "
        "cycles before failure"
    )
    print("=" * 96)
    header = "{:<32} {:>9} {:>8} {:>9} {:>8} {:>8} {:>7} {:>5}".format(
        "candidate", "threshold", "clean", "mean-req", "worst", "burden", "lead", "pass"
    )
    print(header)
    print("-" * len(header))
    for verdict in selection.ranked:
        print(
            "{:<32} {:>9.4f} {:>8.0%} {:>9.0%} {:>8.0%} {:>8.1%} {:>7} {:>5}".format(
                f"{verdict.candidate.value}/{verdict.config_id}",
                verdict.threshold,
                verdict.clean.detection_fraction,
                verdict.mean_detection_required,
                verdict.worst_detection_required,
                verdict.clean.early_alarm_burden,
                f"{verdict.clean.median_lead_time:.0f}" if verdict.clean.median_lead_time else "-",
                "yes" if verdict.qualifies else "no",
            )
        )

    if selection.recommended:
        best = selection.recommended
        print(
            f"\nrecommended: {best.candidate.value}/{best.config_id} "
            f"(clean detection {best.clean.detection_fraction:.0%}, "
            f"95% interval {best.clean.detection_ci.lower:.2f}-{best.clean.detection_ci.upper:.2f}; "
            f"worst required case {best.worst_detection_required:.0%} "
            f"on {best.worst_scenario_id})"
        )
    else:
        print("\nNo candidate met the criteria. No model is recommended.")

    for note in selection.notes:
        print(f"note: {note}")
    for item in selection.uncertain_comparisons:
        print(f"uncertain: {item}")
    for verdict in selection.ranked:
        for note in verdict.notes:
            print(f"  {verdict.candidate.value}/{verdict.config_id}: {note}")


if __name__ == "__main__":
    raise SystemExit(main())
