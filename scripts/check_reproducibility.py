"""Run the evaluation twice and compare every metric, then record the result."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import EXPERIMENT, ExperimentConfig, get_settings  # noqa: E402
from app.data.loader import load_dataset  # noqa: E402
from app.data.synthetic import make_synthetic_dataset  # noqa: E402
from app.evidence.bundle import load_bundle, write_bundle  # noqa: E402
from app.evidence.store import EvidenceStore, compare_runs  # noqa: E402
from app.scoring.pipeline import EvaluationResult, evaluate  # noqa: E402
from app.utils.logging_setup import get_logger, setup_logging, timed  # noqa: E402

logger = get_logger("check_reproducibility")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="cmapss", choices=("cmapss", "csv", "synthetic"))
    parser.add_argument("--subset", default="FD001")
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="score the required fault set only. This leaves the frozen configuration "
        "untouched, so the check still attaches to a bundle built from it.",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="also cut folds and configurations. Quicker, but it changes the "
        "configuration fingerprint, so the check will not be attached.",
    )
    parser.add_argument("--tolerance", type=float, default=1e-9)
    parser.add_argument("--no-attach", action="store_true", help="report only; leave the bundle untouched")
    return parser.parse_args(argv)


def metrics_of(result: EvaluationResult) -> dict[str, float]:
    flat: dict[str, float] = {}

    for name, metrics in result.clean.items():
        flat[f"clean.{name}.detection"] = metrics.detection_fraction
        flat[f"clean.{name}.burden"] = metrics.early_alarm_burden
        flat[f"clean.{name}.episodes_per_1000"] = metrics.new_episodes_per_1000
        if metrics.median_lead_time is not None:
            flat[f"clean.{name}.lead"] = float(metrics.median_lead_time)

    for name, threshold in result.thresholds.items():
        flat[f"threshold.{name}"] = float(threshold)

    for scenario in result.scenario_results:
        key = f"{scenario.candidate.value}/{scenario.config_id}/{scenario.scenario_id}"
        flat[f"scenario.{key}.detection"] = scenario.metrics.detection_fraction
        flat[f"scenario.{key}.burden"] = scenario.metrics.early_alarm_burden

    for report in result.calibration:
        flat[f"brier.{report.candidate.value}/{report.config_id}"] = report.brier

    return flat


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()

    config: ExperimentConfig = EXPERIMENT
    if args.fast:
        config = replace(config, holdout_engines=10, n_folds=3, configs_per_candidate=1)
    config.validate()

    if args.source == "synthetic":
        dataset = make_synthetic_dataset(config=config)
    else:
        dataset = load_dataset(args.source, subset=args.subset, path=args.path, config=config)
    logger.info("%s", dataset.describe())

    store = EvidenceStore()
    records = []

    for attempt in (1, 2):
        with timed(logger, f"evaluation {attempt} of 2"):
            result = evaluate(dataset, config=config, include_full_matrix=not (args.required_only or args.fast))
        record = store.start_run(
            "export",
            config=config,
            data_hash=dataset.data_hash,
            params={"purpose": "reproducibility", "attempt": attempt},
            notes=["One of a pair of identical runs compared for determinism."],
        )
        store.log_metrics(record, metrics_of(result))
        records.append(store.get(record.run_id))

    check = compare_runs(records[0], records[1], tolerance=args.tolerance)

    if check.reproduced:
        logger.info("reproduced: %d metrics identical to within %.0e", check.metrics_compared, check.tolerance)
    else:
        logger.error(
            "NOT reproduced: %d metrics compared, largest difference %.3e",
            check.metrics_compared,
            check.max_absolute_difference,
        )

    if not args.no_attach and settings.bundle_path.is_file():
        bundle = load_bundle(settings.bundle_path)
        if bundle.config_fingerprint != config.fingerprint() or bundle.profile.data_hash != dataset.data_hash:
            logger.warning(
                "the bundle was produced under configuration %s but this check ran "
                "under %s, so the check was not attached",
                bundle.config_fingerprint,
                config.fingerprint(),
            )
        else:
            bundle.reproducibility = check
            bundle.runs.extend(records)
            write_bundle(bundle, settings.bundle_path)
            logger.info("attached the check to %s", settings.bundle_path)

    return 0 if check.reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
