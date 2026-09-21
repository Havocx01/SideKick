"""The model selection rule.

The engineer sets a minimum useful detection rate and a maximum early alarm
burden *before* any candidate is scored. A candidate qualifies only if it meets
both on clean data and on every case in the required fault set. Qualifying
candidates are then ranked by mean detection across the required cases, weighting
cases equally, with fewer early alarms breaking ties.

Two properties are deliberate. Nothing is ranked on the strength of clean
performance alone. And "no candidate qualifies" is a valid outcome that the rule
is allowed to return, because a submission that always produces a recommendation
cannot be trusted when it produces one.
"""

from __future__ import annotations

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
    """Whether one measured result satisfies the acceptance criteria."""
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
    """Summarise one candidate against the criteria."""
    notes: list[str] = []
    passes_clean = meets(clean, criteria)
    if not passes_clean:
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
    worst_scenario = min(required, key=lambda r: r.metrics.detection_fraction) if required else None

    if required and len(passed) < len(required):
        failed = len(required) - len(passed)
        notes.append(
            f"{failed} of {len(required)} required fault cases fall short of the criteria"
        )
    if worst_scenario is not None and worst_scenario.metrics.detection_fraction < clean.detection_fraction:
        drop = clean.detection_fraction - worst_scenario.metrics.detection_fraction
        notes.append(
            f"worst case loses {drop:.0%} detection against clean data "
            f"({worst_scenario.scenario_id})"
        )

    return CandidateVerdict(
        candidate=candidate,
        config_id=config_id,
        threshold=threshold,
        clean=clean,
        passes_clean=passes_clean,
        required_scenarios=len(required),
        required_passed=len(passed),
        passes_all_required=bool(required) and len(passed) == len(required),
        mean_detection_required=(sum(detections) / len(detections)) if detections else 0.0,
        worst_detection_required=min(detections) if detections else clean.detection_fraction,
        worst_scenario_id=worst_scenario.scenario_id if worst_scenario else None,
        worst_metrics=worst_scenario.metrics if worst_scenario else None,
        failing_scenarios=[r.scenario_id for r in required if not meets(r.metrics, criteria)],
        qualifies=passes_clean and bool(required) and len(passed) == len(required),
        notes=notes,
    )


def select(
    verdicts: list[CandidateVerdict],
    criteria: AcceptanceCriteria,
    *,
    partition: Partition = Partition.out_of_fold,
) -> SelectionResult:
    """Rank candidates and recommend one, or decline to recommend any."""
    ranked = sorted(
        verdicts,
        key=lambda v: (
            not v.qualifies,
            -v.mean_detection_required,
            v.clean.early_alarm_burden,
            v.candidate.value,
        ),
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
        # Flag orderings the data does not actually establish.
        for better, worse in zip(qualifying, qualifying[1:], strict=False):
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
