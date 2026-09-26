"""Score the held-back equipment once, and attach the result to the evidence bundle."""

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
from app.schemas import AlertMetrics, CandidateVerdict, FaultSpec, Partition, ScenarioResult  # noqa: E402
from app.scoring.metrics import aggregate, score_engine  # noqa: E402
from app.scoring.selection import build_verdict, select  # noqa: E402
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
        "--include-baseline", action="store_true", help="also score the age baseline as a fixed reference"
    )
    parser.add_argument("--bundle", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="report the result without writing it into the bundle")
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
    featureNames = builder.feature_names()
    equipmentIds = sorted(blocks)

    cleanDesign = design_from_blocks(blocks, featureNames, equipment_ids=equipmentIds)
    cleanScores = candidate.score(cleanDesign)
    cleanScorings = [
        score_engine(
            equipmentId,
            cleanScores[cleanDesign.equipment_id == equipmentId],
            cleanDesign.cycle[cleanDesign.equipment_id == equipmentId],
            cleanDesign.rul[cleanDesign.equipment_id == equipmentId],
            threshold,
            config=config,
        )
        for equipmentId in equipmentIds
    ]
    clean = aggregate(cleanScorings, config=config)

    results: list[ScenarioResult] = []
    for spec in scenarios:
        if spec.sensor not in builder.preprocessor.sensors:
            continue
        index = builder.preprocessor.index_of(spec.sensor)
        std = builder.preprocessor.std_of(spec.sensor)

        scorings = []
        for equipmentId in equipmentIds:
            block = blocks[equipmentId]
            injected = apply_fault(
                dataset.sensor_matrix(equipmentId)[:, index], block.rul, spec, sensor_std=std, config=config
            )
            if not injected.applied:
                # An engine too short to reach the onset is skipped, not counted as
                # a detection. Counting it either way would be a fabricated result.
                continue
            features = block.features.copy()
            builder.rebuild_sensor(features, injected.values, spec.sensor)
            faulted = EngineBlock(
                equipment_id=equipmentId,
                features=features,
                labels=block.labels,
                cycles=block.cycles,
                rul=block.rul,
                rows=block.rows,
                scorable=block.scorable,
            )
            design = design_from_blocks({equipmentId: faulted}, featureNames, equipment_ids=[equipmentId])
            scorings.append(
                score_engine(equipmentId, candidate.score(design), design.cycle, design.rul, threshold, config=config)
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

    return clean, results, cleanDesign.y, cleanScores


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()

    bundlePath = args.bundle or settings.bundle_path
    if not bundlePath.is_file():
        logger.error("no bundle at %s. Run scripts/run_pipeline.py first.", bundlePath)
        return 1
    bundle = load_bundle(bundlePath)
    if bundle.final_evaluation is not None:
        logger.error("This bundle already contains a final evaluation. Refusing to rescore it.")
        return 1
    # Rebuilding development evidence must not make an exposed holdout "fresh".
    for archivedPath in sorted((bundlePath.parent / "archive").glob("*.json")):
        archived = load_bundle(archivedPath)
        if (
            archived.final_evaluation is not None
            and archived.profile.data_hash == bundle.profile.data_hash
            and set(archived.splits.holdout) == set(bundle.splits.holdout)
        ):
            logger.error(
                "The archived evaluation %s already exposed this holdout. Use new independent data for final validation.",
                archivedPath.name,
            )
            return 1

    config = ExperimentConfig(**{k: v for k, v in bundle.config.items() if hasattr(EXPERIMENT, k)})
    config.validate()
    if config.fingerprint() != bundle.config_fingerprint:
        logger.error(
            "the bundle's configuration does not fingerprint to %s. Refusing to score "
            "the holdout against settings that have changed since.",
            bundle.config_fingerprint,
        )
        return 1

    developmentSelection = bundle.development_selection
    recommended = developmentSelection.recommended
    recommendedName = f"{recommended.candidate.value}/{recommended.config_id}" if recommended else None
    if args.candidate and args.candidate != recommendedName:
        logger.error("Only the candidate selected during development may be scored on the holdout.")
        return 1
    chosen = args.candidate or (
        f"{recommended.candidate.value}/{recommended.config_id}" if recommended is not None else None
    )
    if chosen is None:
        logger.error(
            "development recommended no candidate, so there is nothing the holdout "
            "should be spent on. Scoring it now would be searching for a winner on "
            "the one partition reserved for reporting."
        )
        return 1

    thresholds = {f"{v.candidate.value}/{v.config_id}": v.threshold for v in developmentSelection.ranked}
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
    criteria = developmentSelection.criteria
    store = EvidenceStore()

    verdicts: list[CandidateVerdict] = []
    allResults: list[ScenarioResult] = []
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
        scenarios = required_scenarios([s for s in builder.sensors if builder.preprocessor.std_of(s) > 0], config)
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
        allResults.extend(results)
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
            notes=["Scored once. The threshold was fixed on development data and not retuned here."],
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

    # A reference baseline must never replace the development nominee here.
    final = select(verdicts[:1], criteria, partition=Partition.holdout)
    final.ranked.extend(verdicts[1:])
    final.notes.insert(
        0,
        f"Scored once on {len(splits.holdout)} held-back engines, using the candidate "
        "and threshold that development had already chosen. No selection was made here.",
    )

    if args.dry_run:
        logger.info("dry run: the bundle was not modified")
        return 0

    bundle.final_evaluation = final
    bundle.scenario_results = [r for r in bundle.scenario_results if r.partition != Partition.holdout] + allResults
    bundle.calibration = [r for r in bundle.calibration if r.partition != Partition.holdout] + reports
    bundle.runs = store.list_runs(limit=80)
    write_bundle(bundle, bundlePath)
    logger.info("attached the held-out evaluation to %s", bundlePath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
