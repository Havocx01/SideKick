"""Score the held-back equipment once, and attach the result to the evidence bundle.

Everything on the comparison view up to this point is a development number: the
thresholds were chosen on it, the candidates were ranked on it, and the winner was
selected on it. Reporting those as expected field performance would be reporting
the best of many attempts.

So this script runs once, after the configuration is frozen, and it scores **only
the candidate that development already chose**. Scoring all ten here and then
picking the best would reintroduce exactly the selection pressure the holdout
exists to escape. The age baseline can be added as a fixed reference, because it
was never a selection option and reads no sensor at all.

The models are refit on every development engine, with preprocessing statistics
taken from the development engines alone, so the held-back histories are never an
input to anything — only ever an input to scoring.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import EXPERIMENT, ExperimentConfig, get_settings  # noqa: E402
from app.data.loader import load_dataset  # noqa: E402
from app.evidence.bundle import load_bundle, write_bundle  # noqa: E402
from app.evidence.store import EvidenceStore  # noqa: E402
from app.evidence.tracking import mirror_run  # noqa: E402
from app.faults.inject import apply_fault  # noqa: E402
from app.faults.matrix import required_scenarios  # noqa: E402
from app.models.base import Candidate  # noqa: E402
from app.models.calibration import calibration_report  # noqa: E402
from app.models.candidates import candidate_grid  # noqa: E402
from app.models.design import EngineBlock, design_from_blocks, engine_blocks  # noqa: E402
from app.models.splits import make_splits  # noqa: E402
from app.models.train import fit_final  # noqa: E402
from app.schemas import (  # noqa: E402
    AlertMetrics,
    CandidateVerdict,
    FaultSpec,
    Partition,
    ScenarioResult,
)
from app.scoring.metrics import aggregate, score_engine  # noqa: E402
from app.scoring.selection import build_verdict, default_criteria, select  # noqa: E402
from app.utils.logging_setup import get_logger, setup_logging, timed  # noqa: E402

logger = get_logger("score_holdout")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="cmapss", choices=("cmapss", "csv"))
    parser.add_argument("--subset", default="FD001")
    parser.add_argument("--path", type=Path, default=None, help="CSV path when --source csv")
    parser.add_argument(
        "--candidate",
        default=None,
        help="candidate name to score, as 'family/config'. Defaults to whatever "
        "development recommended, which is the disciplined choice.",
    )
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        help="also score the age baseline as a fixed reference",
    )
    parser.add_argument("--bundle", type=Path, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the result without writing it into the bundle",
    )
    return parser.parse_args(argv)


def score_scenarios(
    *,
    candidate: Candidate,
    builder,
    dataset,
    blocks: dict[str, EngineBlock],
    threshold: float,
    scenarios: list[FaultSpec],
    config: ExperimentConfig,
) -> tuple[AlertMetrics, list[ScenarioResult], np.ndarray, np.ndarray]:
    """Clean and per-scenario measures for one candidate on the held-back engines."""
    feature_names = builder.feature_names()
    equipment_ids = sorted(blocks)

    clean_design = design_from_blocks(blocks, feature_names, equipment_ids=equipment_ids)
    clean_scores = candidate.score(clean_design)
    clean_scorings = [
        score_engine(
            equipment_id,
            clean_scores[clean_design.equipment_id == equipment_id],
            clean_design.cycle[clean_design.equipment_id == equipment_id],
            clean_design.rul[clean_design.equipment_id == equipment_id],
            threshold,
            config=config,
        )
        for equipment_id in equipment_ids
    ]
    clean = aggregate(clean_scorings, config=config)

    results: list[ScenarioResult] = []
    for spec in scenarios:
        if spec.sensor not in builder.preprocessor.sensors:
            continue
        index = builder.preprocessor.index_of(spec.sensor)
        std = builder.preprocessor.std_of(spec.sensor)

        scorings = []
        for equipment_id in equipment_ids:
            block = blocks[equipment_id]
            injected = apply_fault(
                dataset.sensor_matrix(equipment_id)[:, index],
                block.rul,
                spec,
                sensor_std=std,
                config=config,
            )
            if not injected.applied:
                # An engine too short to reach the onset is skipped, not counted as
                # a detection. Counting it either way would be a fabricated result.
                continue
            features = block.features.copy()
            builder.rebuild_sensor(features, injected.values, spec.sensor)
            faulted = EngineBlock(
                equipment_id=equipment_id,
                features=features,
                labels=block.labels,
                cycles=block.cycles,
                rul=block.rul,
                rows=block.rows,
                scorable=block.scorable,
            )
            design = design_from_blocks(
                {equipment_id: faulted}, feature_names, equipment_ids=[equipment_id]
            )
            scorings.append(
                score_engine(
                    equipment_id,
                    candidate.score(design),
                    design.cycle,
                    design.rul,
                    threshold,
                    config=config,
                )
            )

        if not scorings:
            continue
        results.append(
            ScenarioResult(
                scenario_id=spec.scenario_id,
                candidate=candidate.kind,
                config_id=candidate.config_id,
                partition=Partition.holdout,
                threshold=threshold,
                fault=spec,
                metrics=aggregate(scorings, config=config),
                required=True,
            )
        )

    return clean, results, clean_design.y, clean_scores


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()

    bundle_path = args.bundle or settings.bundle_path
    if not bundle_path.is_file():
        logger.error("no bundle at %s. Run scripts/run_pipeline.py first.", bundle_path)
        return 1
    bundle = load_bundle(bundle_path)

    config = ExperimentConfig(**{k: v for k, v in bundle.config.items() if hasattr(EXPERIMENT, k)})
    config.validate()
    if config.fingerprint() != bundle.config_fingerprint:
        logger.error(
            "the bundle's configuration does not fingerprint to %s. Refusing to score "
            "the holdout against settings that have changed since.",
            bundle.config_fingerprint,
        )
        return 1

    development_selection = bundle.development_selection
    recommended = development_selection.recommended
    chosen = args.candidate or (
        f"{recommended.candidate.value}/{recommended.config_id}"
        if recommended is not None
        else None
    )
    if chosen is None:
        logger.error(
            "development recommended no candidate, so there is nothing the holdout "
            "should be spent on. Scoring it now would be searching for a winner on "
            "the one partition reserved for reporting."
        )
        return 1

    thresholds = {
        f"{v.candidate.value}/{v.config_id}": v.threshold for v in development_selection.ranked
    }
    wanted = [chosen]
    if args.include_baseline:
        wanted += [name for name in thresholds if name.startswith("age_baseline/")]
    wanted = list(dict.fromkeys(name for name in wanted if name in thresholds))
    if not wanted:
        logger.error("%s is not in the recorded development ranking", chosen)
        return 1

    dataset = load_dataset(args.source, subset=args.subset, path=args.path, config=config)
    if dataset.data_hash != bundle.profile.data_hash:
        logger.error(
            "data hash %s does not match the bundle's %s. The partitions would differ, "
            "so the held-back engines would no longer be the ones held back.",
            dataset.data_hash,
            bundle.profile.data_hash,
        )
        return 1

    splits = make_splits(dataset, config)
    if sorted(splits.holdout) != sorted(bundle.splits.holdout):
        logger.error("the recomputed partition does not match the bundle's. Refusing to score.")
        return 1

    grid = {candidate.name: candidate for candidate in candidate_grid(config)}
    holdout = dataset.subset(splits.holdout)
    criteria = default_criteria(config)
    store = EvidenceStore()

    verdicts: list[CandidateVerdict] = []
    all_results: list[ScenarioResult] = []
    reports = []

    for name in wanted:
        template = grid.get(name)
        if template is None:
            logger.error("%s is not in the current candidate grid", name)
            return 1

        with timed(logger, f"refitting {name} on {len(splits.development)} development engines"):
            fitted, builder, _ = fit_final(dataset, splits, template, config=config)

        # Features for the held-back engines, built with development-only statistics.
        blocks = engine_blocks(holdout, builder)
        scenarios = required_scenarios(
            [s for s in builder.sensors if builder.preprocessor.std_of(s) > 0], config
        )
        threshold = thresholds[name]

        with timed(logger, f"scoring {name} on the holdout over {len(scenarios)} scenarios"):
            clean, results, labels, scores = score_scenarios(
                candidate=fitted,
                builder=builder,
                dataset=holdout,
                blocks=blocks,
                threshold=threshold,
                scenarios=scenarios,
                config=config,
            )

        verdict = build_verdict(
            candidate=fitted.kind,
            config_id=fitted.config_id,
            threshold=threshold,
            clean=clean,
            required=results,
            criteria=criteria,
        )
        verdicts.append(verdict)
        all_results.extend(results)
        reports.append(
            calibration_report(
                candidate=fitted.kind,
                config_id=fitted.config_id,
                labels=labels,
                scores=scores,
                partition=Partition.holdout,
            )
        )

        record = store.start_run(
            "final_evaluation",
            config=config,
            data_hash=dataset.data_hash,
            params={
                "candidate": name,
                "threshold": threshold,
                "engines": len(splits.holdout),
                "scenarios": len(results),
                "partition": Partition.holdout.value,
                "threshold_source": "development out-of-fold",
            },
            notes=[
                "Scored once. The threshold was fixed on development data and not "
                "retuned here.",
            ],
        )
        store.log_metrics(
            record,
            {
                "clean_detection": clean.detection_fraction,
                "clean_burden": clean.early_alarm_burden,
                "worst_required_detection": verdict.worst_detection_required,
                "mean_required_detection": verdict.mean_detection_required,
            },
        )
        mirror_run(record)

        logger.info(
            "%s on %d held-back engines: clean %.0f%% (%.2f-%.2f), worst required %.0f%% (%s)",
            name,
            clean.engines,
            100 * clean.detection_fraction,
            clean.detection_ci.lower,
            clean.detection_ci.upper,
            100 * verdict.worst_detection_required,
            verdict.worst_scenario_id or "none",
        )

    final = select(verdicts, criteria, partition=Partition.holdout)
    final.notes.insert(
        0,
        f"Scored once on {len(splits.holdout)} held-back engines, using the candidate "
        "and threshold that development had already chosen. No selection was made here.",
    )

    if args.dry_run:
        logger.info("dry run: the bundle was not modified")
        return 0

    bundle.final_evaluation = final
    bundle.scenario_results = [
        r for r in bundle.scenario_results if r.partition != Partition.holdout
    ] + all_results
    bundle.calibration = [
        r for r in bundle.calibration if r.partition != Partition.holdout
    ] + reports
    bundle.runs = store.list_runs(limit=80)
    write_bundle(bundle, bundle_path)
    logger.info("attached the held-out evaluation to %s", bundle_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
