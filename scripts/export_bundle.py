"""Rebuild the deployable evidence bundle, and check it before it ships."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dataclasses import fields  # noqa: E402

from app.config import ExperimentConfig, get_settings  # noqa: E402
from app.evidence.bundle import load_bundle, write_bundle  # noqa: E402
from app.schemas import EvidenceBundle  # noqa: E402
from app.utils.jsonio import hash_file  # noqa: E402
from app.utils.logging_setup import get_logger, setup_logging  # noqa: E402

logger = get_logger("export_bundle")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=None, help="bundle to read (default: evidence/bundle.json)")
    parser.add_argument("--out", type=Path, default=None, help="where to write (default: in place)")
    parser.add_argument(
        "--check-only", action="store_true", help="verify the bundle and report, without writing anything"
    )
    return parser.parse_args(argv)


def _known_fields(config: dict) -> dict:
    known = {field.name for field in fields(ExperimentConfig)}
    return {key: tuple(value) if isinstance(value, list) else value for key, value in config.items() if key in known}


def inspect(bundle: EvidenceBundle) -> list[str]:
    problems: list[str] = []

    # Reject a fingerprint that does not match the recorded configuration.
    expected = ExperimentConfig(**_known_fields(bundle.config)).fingerprint()
    if bundle.config_fingerprint != expected:
        problems.append(
            f"config fingerprint {bundle.config_fingerprint} does not match the recorded "
            f"settings, which fingerprint to {expected}"
        )

    selection = bundle.development_selection
    recommended = selection.recommended
    if selection.outcome.value == "qualified" and recommended is None:
        problems.append("the outcome is 'qualified' but no candidate is recommended")
    if recommended is not None and not recommended.qualifies:
        problems.append(f"{recommended.candidate.value} is recommended but is not marked as qualifying")

    # Each ranked candidate needs supporting scenario records.
    ranked = {(v.candidate.value, v.config_id) for v in selection.ranked}
    scored = {(r.candidate.value, r.config_id) for r in bundle.scenario_results}
    for candidate in sorted(ranked - scored):
        problems.append(f"{candidate[0]}/{candidate[1]} is ranked but has no scenario results")

    if not bundle.replay_series:
        problems.append("no replay series: the warning replay view would be empty")
    if not bundle.limitations:
        problems.append("no limitations recorded")
    if not bundle.runs:
        problems.append("no run records: nothing in the bundle is traceable to a run")

    # Equipment partitions must remain disjoint in the exported artifact.
    overlap = set(bundle.splits.holdout) & set(bundle.splits.development)
    if overlap:
        problems.append(f"{len(overlap)} engines appear in both the holdout and development sets")

    replayEngines = {series.equipment_id for series in bundle.replay_series}
    development = set(bundle.splits.development)
    stray = replayEngines - development - set(bundle.splits.holdout)
    if stray:
        problems.append(f"replay covers engines that are in no partition: {sorted(stray)}")

    return problems


def summarise(bundle: EvidenceBundle, path: Path) -> None:
    selection = bundle.development_selection
    recommended = selection.recommended
    sizeKb = path.stat().st_size / 1024

    logger.info("bundle           %s (%.0f KB, sha %s)", path, sizeKb, hash_file(path))
    logger.info("dataset          %s (hash %s)", bundle.profile.dataset_id, bundle.profile.data_hash)
    logger.info("config           %s", bundle.config_fingerprint)
    logger.info("commit           %s", bundle.git_commit or "unknown")
    logger.info("generated        %s", bundle.generated_at.isoformat())
    logger.info(
        "partitions       %d development, %d held back", len(bundle.splits.development), len(bundle.splits.holdout)
    )
    logger.info("scenarios        %d results", len(bundle.scenario_results))
    logger.info("replay           %d series", len(bundle.replay_series))
    logger.info("explanations     %d", len(bundle.explanations))
    logger.info("runs             %d", len(bundle.runs))
    logger.info("outcome          %s", selection.outcome.value)
    if recommended is not None:
        logger.info(
            "recommended      %s/%s: clean %.0f%%, worst required %.0f%% (%s)",
            recommended.candidate.value,
            recommended.config_id,
            100 * recommended.clean.detection_fraction,
            100 * recommended.worst_detection_required,
            recommended.worst_scenario_id or "none",
        )
    else:
        logger.info("recommended      none; no candidate met the criteria")
    if bundle.final_evaluation is None:
        logger.info("held-out         not yet scored")
    if bundle.reproducibility is not None:
        check = bundle.reproducibility
        logger.info(
            "reproducibility  %s (max difference %.2e over %d metrics)",
            "reproduced" if check.reproduced else "DIVERGED",
            check.max_absolute_difference,
            check.metrics_compared,
        )


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    settings = get_settings()
    source = args.bundle or settings.bundle_path

    if not source.is_file():
        logger.error("no bundle at %s. Run scripts/run_pipeline.py first.", source)
        return 1

    bundle = load_bundle(source)
    summarise(bundle, source)

    problems = inspect(bundle)
    if problems:
        logger.error("%d consistency problem(s):", len(problems))
        for problem in problems:
            logger.error("  - %s", problem)
    else:
        logger.info("consistency      all checks passed")

    if not args.check_only:
        destination = args.out or source
        write_bundle(bundle, destination)
        logger.info("wrote            %s", destination)

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
