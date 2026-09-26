"""Building and reading the replay bundle."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.config import EXPERIMENT, ExperimentConfig, get_settings
from app.evidence.store import git_commit
from app.experiments.provenance import source_digest
from app.schemas import AlertExplanation, EvidenceBundle, FaultSpec, ReplaySeries, RunRecord, SelectionResult
from app.utils.jsonio import read_json, write_json
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.scoring.pipeline import EvaluationResult

#: Stated on every report and in the bundle itself. Taken from the proposal's
#: limitations, kept here so they travel with the data rather than living only in
#: a slide deck.
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
    threshold = result.thresholds[candidateName]

    replaySeries = _build_replay(result, candidateName, threshold, replay_engines, replay_fault, config)
    explanations = _build_explanations(result, candidateName, replaySeries)

    return EvidenceBundle(
        schema_version=2,
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

    engines = choose_replay_engines(result.training, candidate_name, threshold, limit=limit, config=config)

    # Default replay to the weakest required scenario.
    if replay_fault is None:
        worst = None
        for scenario in result.scenario_results:
            if not scenario.required or scenario.fault is None:
                continue
            name = f"{scenario.candidate.value}/{scenario.config_id}"
            if name != candidate_name:
                continue
            if worst is None or scenario.metrics.detection_fraction < worst.metrics.detection_fraction:
                worst = scenario
        replay_fault = worst.fault if worst else None

    series: list[ReplaySeries] = []
    for equipmentId in engines:
        clean = build_series(result.training, candidate_name, equipmentId, threshold, spec=None, config=config)
        if clean:
            series.append(clean)
        if replay_fault is not None:
            faulted = build_series(
                result.training, candidate_name, equipmentId, threshold, spec=replay_fault, config=config
            )
            if faulted:
                series.append(faulted)
    return series


def _build_explanations(
    result: EvaluationResult, candidate_name: str, series: list[ReplaySeries]
) -> list[AlertExplanation]:
    from app.models.design import design_from_blocks
    from app.models.explain import explain_alert

    explanations: list[AlertExplanation] = []
    seen: set[tuple[str, int]] = set()

    for entry in series:
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
            explanations.append(explain_alert(candidate, design, int(positions[0])))
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
    return EvidenceBundle.model_validate(read_json(target))
