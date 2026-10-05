"""Short explanations scoped to one candidate and evaluation partition."""

from urllib.parse import urlencode

from app.schemas import CandidateKind, DecisionReport, EvidenceBundle, GuideAnswer, Partition


def candidateLabel(verdict):
    names = {CandidateKind.xgboost: "XGBoost", CandidateKind.xgboost_augmented: "Augmented XGBoost",
             CandidateKind.logistic_regression: "Logistic regression", CandidateKind.age_baseline: "Age baseline"}
    return f"{names[verdict.candidate]} ({verdict.config_id})"


def percentage(value, digits=2):
    return f"{value:.{digits}%}" if value is not None else "unavailable"


def faultLabel(bundle, verdict, partition=Partition.out_of_fold):
    row = next((r for r in bundle.scenario_results if r.scenario_id == verdict.worst_scenario_id
                and r.candidate == verdict.candidate and r.config_id == verdict.config_id and r.partition == partition), None)
    return row.fault.label() if row and row.fault else verdict.worst_scenario_id or "unrecorded fault"


def decision(bundle: EvidenceBundle, candidate: str | None = None, partition=Partition.out_of_fold) -> DecisionReport:
    selection = bundle.final_evaluation if partition == Partition.holdout else bundle.development_selection
    if selection is None:
        raise ValueError("No final validation is available for this experiment.")
    criteria = selection.criteria
    focus = selection.recommended or (selection.ranked[0] if selection.ranked else None)
    if candidate:
        focus = next((v for v in selection.ranked if f"{v.candidate.value}/{v.config_id}" == candidate), None)
        if focus is None:
            raise ValueError("That candidate is unavailable in this evaluation partition.")
    key = f"{focus.candidate.value}/{focus.config_id}" if focus else None
    context = {"candidate": key, "partition": partition.value} if key else {"partition": partition.value}
    prefix = f"/experiments/{bundle.experiment_id}" if bundle.experiment_id else ""
    comparison = f"{prefix}/comparison?{urlencode(context)}"
    replay = f"{prefix}/replay?{urlencode(context)}"
    stage = "final-validation" if partition == Partition.holdout else "development"
    rule = f"{criteria.min_detection_fraction:.1%} detection minimum and {criteria.max_early_alarm_burden:.1%} alarm-burden maximum"
    if focus:
        title = f"{candidateLabel(focus)} {'meets' if focus.qualifies else 'does not meet'} {stage} criteria"
        summary = (f"With healthy sensors, {focus.clean.detected}/{focus.clean.engines} histories received a warning in time. "
                   f"The healthy-sensor results {'meet' if focus.passes_clean else 'do not meet'} the test limits. "
                   f"Time spent warning too early: {percentage(focus.clean.early_alarm_burden)} of eligible early cycles. "
                   f"{focus.required_passed}/{focus.required_scenarios} required fault cases pass the {rule}.")
        if focus.coverage_complete is False:
            summary += " Required-case coverage is incomplete."
        if focus.candidate == CandidateKind.age_baseline:
            summary += " This baseline uses equipment age only, without sensor readings."
    else:
        title, summary = "No candidate results", "No model is recommended."
    summary += " These results do not approve deployment."
    if focus and focus.worst_metrics:
        metrics = focus.worst_metrics
        faultSummary = (f"Lowest detection: {faultLabel(bundle, focus, partition)}. Detection changed from "
                        f"{focus.clean.detection_fraction:.1%} to {metrics.detection_fraction:.1%}. "
                        f"{metrics.detected}/{metrics.engines} histories warned in time; {metrics.late} warned too late; "
                        f"{metrics.missed} missed both the useful and late warning windows. "
                        f"Time spent warning too early in this case: {percentage(metrics.early_alarm_burden)} of eligible early cycles.")
        if focus.worst_burden_required is not None:
            faultSummary += f" Highest required burden: {percentage(focus.worst_burden_required)}."
    else:
        faultSummary = "No required fault result is available."
    ordinary = next((v for v in selection.ranked if v.qualifies and v.candidate == CandidateKind.xgboost), None)
    augmented = next((v for v in selection.ranked if v.qualifies and v.candidate == CandidateKind.xgboost_augmented), None)
    if ordinary and augmented:
        delta = 100 * (augmented.mean_detection_required - ordinary.mean_detection_required)
        augmentation = (f"Best qualifying {candidateLabel(ordinary)} versus {candidateLabel(augmented)}: "
                        f"mean required detection changed by {delta:+.2f} percentage points. "
                        "This compares selected configurations and does not isolate augmentation's effect. "
                        + ("Inspect the matched-configuration comparisons separately." if bundle.paired_comparisons
                         else "No matched experiment is recorded in this historical bundle."))
    else:
        augmentation = "Two qualifying XGBoost families are unavailable in this partition. No improvement claim is supported."
    traces = [s for s in bundle.replay_series if f"{s.candidate.value}/{s.config_id}" == key and s.partition == partition]
    example = next((s for s in traces if s.scenario_id == (focus.worst_scenario_id if focus else None)), None)
    if example:
        replay += "&" + urlencode({"equipment": example.equipment_id, "scenario": example.scenario_id})
    nextAnswer = ("Replay a selected clean/faulted example, then inspect missed warnings, alarm burden and coverage. "
                  "Representative traces do not show every history.") if traces else "No replay is stored for this candidate. Inspect its scenario metrics and export the evidence."
    return DecisionReport(
        title=title, summary=summary, fault_summary=faultSummary, augmentation_summary=augmentation,
        unaugmented=ordinary, augmented=augmented, limitations=[bundle.holdout_status, *bundle.limitations],
        inspected_candidate=key, partition=partition,
        guide=[
            GuideAnswer(question="Why did this model pass or fail?", answer=summary, link=comparison, link_label="Inspect candidate results"),
            GuideAnswer(question="Which fault caused the biggest problem?", answer=faultSummary, link=comparison + "#fault-results", link_label="Inspect fault cases"),
            GuideAnswer(question="Did augmented training help?", answer=augmentation, link=comparison + "#augmentation", link_label="Compare configurations"),
            GuideAnswer(question="What should I inspect next?", answer=nextAnswer, link=replay if traces else comparison + "#fault-results", link_label="Open warning replay" if traces else "Inspect fault metrics"),
        ],
    )
