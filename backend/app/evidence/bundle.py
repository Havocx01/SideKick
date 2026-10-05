"""Building and reading the replay bundle."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.config import EXPERIMENT, ExperimentConfig, get_settings
from app.evidence.store import git_commit
from app.experiments.provenance import source_digest
from app.schemas import AlertExplanation, EvidenceBundle, ExperimentProtocol, FaultSpec, ReplaySeries, RunRecord, SelectionResult
from app.utils.jsonio import read_json, write_json
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.scoring.pipeline import EvaluationResult

# Limitations travel with exported evidence.
LIMITATIONS = [
    "FD001 is simulated aerospace data under one operating condition and one fault "
    "mode. It does not validate behaviour on ABB motors or pumps.",
    "Injected fault severities are plausible but not calibrated against field "
    "measurements. They need input from maintenance engineers to be realistic.",
    "Feature attributions describe what moved a model's score, not which physical component is failing.",
    "Score calibration can deteriorate under sensor faults, so scores should be "
    "read as rankings rather than probabilities unless the reliability plot supports "
    "otherwise.",
    "Twenty held-out engines give wide intervals. Small differences between "
    "candidates are not established by this evaluation.",
    "Histories are assumed complete. Censored histories, where the machine had not "
    "failed by the last reading, need a different protocol.",
    "A run in which no candidate meets the criteria is a valid outcome, not a malfunction.",
]


def build_bundle(
    result: EvaluationResult,
    *,
    config: ExperimentConfig = EXPERIMENT,
    runs: list[RunRecord] | None = None,
    final_evaluation: SelectionResult | None = None,
    replay_engines: int = 6,
    replay_fault: FaultSpec | None = None,
    reproducibility=None,
) -> EvidenceBundle:
    config = result.training.config
    recommended = result.selection.recommended
    candidateName = (
        f"{recommended.candidate.value}/{recommended.config_id}"
        if recommended
        else result.selection.ranked[0].candidate.value + "/" + result.selection.ranked[0].config_id
    )

    replaySeries = []
    for verdict in result.selection.ranked:
        name = f"{verdict.candidate.value}/{verdict.config_id}"
        replaySeries.extend(_build_replay(result, name, result.thresholds[name], min(3, replay_engines), replay_fault, config))
    explanations = _build_explanations(result, candidateName, replaySeries)
    from app.scoring.paired import paired_comparisons

    return EvidenceBundle(
        schema_version=3,
        source_digest=source_digest(),
        confirmed_mapping=result.training.dataset.mapping,
        holdout_status=(
            "Holdout scored; these equipment histories are exposed."
            if final_evaluation
            else "No holdout scores are attached. Check prior exposure before any final evaluation."
        ),
        config=config.as_dict(),
        config_fingerprint=config.fingerprint(),
        git_commit=git_commit(),
        profile=result.profile,
        splits=result.training.splits,
        candidates=[candidate.spec() for candidate in result.training.specs.values()],
        development_selection=result.selection,
        final_evaluation=final_evaluation,
        scenario_results=result.scenario_results,
        calibration=result.calibration,
        replay_series=replaySeries,
        explanations=explanations,
        runs=list(runs or []),
        reproducibility=reproducibility,
        limitations=list(LIMITATIONS),
        paired_comparisons=paired_comparisons(result),
        protocol=ExperimentProtocol(
            min_useful_lead=config.min_useful_lead, horizon_cycles=config.horizon_cycles,
            transition_band_end=config.transition_band_end, min_detection_fraction=config.min_detection_fraction,
            max_early_alarm_burden=config.max_early_alarm_burden, base_seed=config.base_seed,
            scenarios=list(config.fault_scenarios),
        ) if config.fault_scenarios is not None else None,
    )


def _build_replay(
    result: EvaluationResult,
    candidate_name: str,
    threshold: float,
    limit: int,
    replay_fault: FaultSpec | None,
    config: ExperimentConfig,
) -> list[ReplaySeries]:
    from app.evidence.replay import build_series, choose_replay_engines

    required = [r for r in result.scenario_results if r.required and r.fault is not None
                and f"{r.candidate.value}/{r.config_id}" == candidate_name]
    if not required:
        return []
    weakest = min(required, key=lambda r: (r.metrics.detection_fraction, r.scenario_id))
    highest = max(required, key=lambda r: (r.metrics.early_alarm_burden or 0, r.scenario_id))
    targets = [(replay_fault or weakest.fault, "Weakest detection"), (highest.fault, "Highest alarm burden")]
    series = {}
    for spec, reason in targets:
        scorings = result.matrix.equipment_metrics.get((candidate_name, spec.scenario_id), [])
        if reason == "Weakest detection":
            ranked = sorted(scorings, key=lambda s: (not s.outcome.missed, not s.outcome.late, s.outcome.equipment_id))
        else:
            ranked = sorted(scorings, key=lambda s: (-s.alarm_eligible_cycles / max(1, s.eligible_cycles), s.outcome.equipment_id))
        engines = [s.outcome.equipment_id for s in ranked[:limit]]
        if not engines:
            engines = choose_replay_engines(result.training, candidate_name, threshold, limit=limit, config=config)
        for equipmentId in engines:
            for fault in (None, spec):
                entry = build_series(result.training, candidate_name, equipmentId, threshold, spec=fault, config=config)
                if entry:
                    entry.representative_reason = reason
                    series[(equipmentId, entry.scenario_id)] = entry
    return list(series.values())


def _build_explanations(
    result: EvaluationResult, candidate_name: str, series: list[ReplaySeries]
) -> list[AlertExplanation]:
    from app.models.design import design_from_blocks
    from app.models.explain import explain_alert

    explanations: list[AlertExplanation] = []
    seen: set[tuple[str, int]] = set()

    for entry in series:
        if f"{entry.candidate.value}/{entry.config_id}" != candidate_name:
            continue
        # Original readings can explain only the clean history.
        if entry.fault is not None:
            continue
        if not entry.episodes:
            continue
        targetCycle = entry.episodes[0].start_cycle
        key = (entry.equipment_id, targetCycle)
        if key in seen:
            continue
        seen.add(key)
        try:
            fold = result.training.fold_for(entry.equipment_id)
            candidate = fold.candidates[candidate_name]
            block = fold.blocks[entry.equipment_id]
            design = design_from_blocks(
                {entry.equipment_id: block}, fold.builder.feature_names(), equipment_ids=[entry.equipment_id]
            )
            positions = (design.cycle == targetCycle).nonzero()[0]
            if positions.size == 0:
                continue
            explanation = explain_alert(candidate, design, int(positions[0]))
            explanation.candidate = candidate_name
            explanations.append(explanation)
        except Exception as exc:  # pragma: no cover - explanation is not load-bearing
            logger.warning("explanation failed for %s: %s", entry.equipment_id, exc)
    return explanations


def write_bundle(bundle: EvidenceBundle, path: Path | None = None) -> Path:
    target = Path(path) if path else get_settings().bundle_path
    write_json(target, bundle.model_dump(mode="json"))
    sizeMb = target.stat().st_size / 1e6
    logger.info("wrote evidence bundle to %s (%.2f MB)", target, sizeMb)
    if sizeMb > 40:
        logger.warning(
            "the bundle is %.1f MB; trim replay series before committing so the "
            "source archive stays under the 50 MB submission limit",
            sizeMb,
        )
    return target


def load_bundle(path: Path | None = None) -> EvidenceBundle:
    target = Path(path) if path else get_settings().bundle_path
    if not target.exists():
        raise FileNotFoundError(
            f"no evidence bundle at {target}. Run 'python scripts/run_pipeline.py' "
            "locally to generate one, or set SIDEKICK_BUNDLE_PATH."
        )
    bundle = EvidenceBundle.model_validate(read_json(target))
    # Derive newly displayed fields from stored metrics without rewriting history.
    for selection in (bundle.development_selection, bundle.final_evaluation):
        if selection is None:
            continue
        for verdict in selection.ranked:
            rows = [r for r in bundle.scenario_results if r.partition == selection.partition and r.required
                    and r.candidate == verdict.candidate and r.config_id == verdict.config_id]
            if rows and verdict.worst_burden_scenario_id is None:
                available = [r for r in rows if r.metrics.early_alarm_burden is not None]
                if available:
                    worst = max(available, key=lambda r: (r.metrics.early_alarm_burden, r.scenario_id))
                    verdict.worst_burden_required = worst.metrics.early_alarm_burden
                    verdict.worst_burden_scenario_id = worst.scenario_id
    return bundle
