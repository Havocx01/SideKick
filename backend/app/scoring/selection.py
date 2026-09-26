"""The model selection rule."""

from __future__ import annotations

from itertools import pairwise

from app.config import EXPERIMENT, ExperimentConfig
from app.schemas import (
    AcceptanceCriteria,
    AlertMetrics,
    CandidateVerdict,
    Partition,
    ScenarioResult,
    SelectionOutcome,
    SelectionResult,
)
from app.scoring.stats import intervals_overlap


def default_criteria(config: ExperimentConfig = EXPERIMENT) -> AcceptanceCriteria:
    return AcceptanceCriteria(
        min_detection_fraction=config.min_detection_fraction,
        max_early_alarm_burden=config.max_early_alarm_burden,
        min_useful_lead=config.min_useful_lead,
        horizon_cycles=config.horizon_cycles,
    )


def meets(metrics: AlertMetrics, criteria: AcceptanceCriteria) -> bool:
    return (
        metrics.detection_fraction >= criteria.min_detection_fraction
        and metrics.early_alarm_burden <= criteria.max_early_alarm_burden
    )


def build_verdict(
    *,
    candidate,
    config_id: str,
    threshold: float,
    clean: AlertMetrics,
    required: list[ScenarioResult],
    criteria: AcceptanceCriteria,
) -> CandidateVerdict:
    notes: list[str] = []
    passesClean = meets(clean, criteria)
    if not passesClean:
        if clean.detection_fraction < criteria.min_detection_fraction:
            notes.append(
                f"clean detection {clean.detection_fraction:.0%} is below the required "
                f"{criteria.min_detection_fraction:.0%}"
            )
        if clean.early_alarm_burden > criteria.max_early_alarm_burden:
            notes.append(
                f"clean early alarm burden {clean.early_alarm_burden:.1%} exceeds the "
                f"permitted {criteria.max_early_alarm_burden:.1%}"
            )

    detections = [r.metrics.detection_fraction for r in required]
    passed = [r for r in required if meets(r.metrics, criteria)]
    worstScenario = min(required, key=lambda r: r.metrics.detection_fraction) if required else None

    if required and len(passed) < len(required):
        failed = len(required) - len(passed)
        notes.append(f"{failed} of {len(required)} required fault cases fall short of the criteria")
    if worstScenario is not None and worstScenario.metrics.detection_fraction < clean.detection_fraction:
        drop = clean.detection_fraction - worstScenario.metrics.detection_fraction
        notes.append(f"worst case loses {drop:.0%} detection against clean data ({worstScenario.scenario_id})")

    return CandidateVerdict(
        candidate=candidate,
        config_id=config_id,
        threshold=threshold,
        clean=clean,
        passes_clean=passesClean,
        required_scenarios=len(required),
        required_passed=len(passed),
        passes_all_required=bool(required) and len(passed) == len(required),
        mean_detection_required=(sum(detections) / len(detections)) if detections else 0.0,
        worst_detection_required=min(detections) if detections else clean.detection_fraction,
        worst_scenario_id=worstScenario.scenario_id if worstScenario else None,
        worst_metrics=worstScenario.metrics if worstScenario else None,
        failing_scenarios=[r.scenario_id for r in required if not meets(r.metrics, criteria)],
        qualifies=passesClean and bool(required) and len(passed) == len(required),
        notes=notes,
    )


def select(
    verdicts: list[CandidateVerdict], criteria: AcceptanceCriteria, *, partition: Partition = Partition.out_of_fold
) -> SelectionResult:
    ranked = sorted(
        verdicts,
        key=lambda v: (not v.qualifies, -v.mean_detection_required, v.clean.early_alarm_burden, v.candidate.value),
    )

    qualifying = [v for v in ranked if v.qualifies]
    notes: list[str] = []
    uncertain: list[str] = []

    if not qualifying:
        notes.append(
            "No candidate met the acceptance criteria on clean data and every "
            "required fault case. No model is recommended."
        )
    elif len(qualifying) > 1:
        for better, worse in pairwise(qualifying):
            if intervals_overlap(better.clean.detection_ci, worse.clean.detection_ci):
                uncertain.append(
                    f"{better.candidate.value}/{better.config_id} vs "
                    f"{worse.candidate.value}/{worse.config_id}: detection intervals "
                    "overlap, so this ordering is not established by the data"
                )

    if qualifying and qualifying[0].clean.engines < 30:
        notes.append(
            f"Ranking rests on {qualifying[0].clean.engines} engines. Intervals are "
            "wide at this size and small differences should not be read as real."
        )

    return SelectionResult(
        outcome=SelectionOutcome.qualified if qualifying else SelectionOutcome.none_qualified,
        criteria=criteria,
        ranked=ranked,
        recommended=qualifying[0] if qualifying else None,
        partition=partition,
        notes=notes,
        uncertain_comparisons=uncertain,
    )
