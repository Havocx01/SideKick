"""Fixed explanations derived only from the selected evidence bundle."""

from urllib.parse import urlencode

from app.schemas import CandidateKind, DecisionReport, EvidenceBundle, GuideAnswer


def candidateLabel(verdict):
    names = {
        CandidateKind.xgboost: "XGBoost",
        CandidateKind.xgboost_augmented: "Augmented XGBoost",
        CandidateKind.logistic_regression: "Logistic regression",
        CandidateKind.age_baseline: "Age baseline",
    }
    return f"{names[verdict.candidate]} ({verdict.config_id})"


def faultLabel(bundle, verdict):
    row = next((r for r in bundle.scenario_results if r.scenario_id == verdict.worst_scenario_id
                and r.candidate == verdict.candidate and r.config_id == verdict.config_id), None)
    if row and row.fault:
        return row.fault.label().replace("sensor_", "sensor ").replace("op_setting_", "operating setting ")
    return verdict.worst_scenario_id or "unrecorded fault"


def decision(bundle: EvidenceBundle) -> DecisionReport:
    selection = bundle.development_selection
    criteria = selection.criteria
    chosen = selection.recommended
    prefix = f"/experiments/{bundle.experiment_id}" if bundle.experiment_id else ""
    comparison = f"{prefix}/comparison"
    replay = f"{prefix}/replay"

    rule = (
        f"at least {criteria.min_detection_fraction:.1%} useful detection and at most "
        f"{criteria.max_early_alarm_burden:.1%} early-alarm burden on clean data and every required fault case"
    )
    if chosen:
        title = f"{candidateLabel(chosen)} met the selected criteria"
        summary = (
            f"It met {rule}. Qualifying candidates are ranked by mean detection across required "
            f"fault cases, with clean early-alarm burden breaking ties. Its clean detection was "
            f"{chosen.clean.detection_fraction:.1%}, with {chosen.clean.early_alarm_burden:.2%} early-alarm burden. These are development results, not deployment approval."
        )
    else:
        title = "No model qualified"
        summary = f"No candidate met {rule}. No model is recommended. Inspect the required cases for the leading candidates before changing the criteria or collecting more data."
    focus = chosen or (selection.ranked[0] if selection.ranked else None)
    if focus and focus.worst_metrics:
        faultSummary = (
            f"For {candidateLabel(focus)}, the required case with lowest detection was "
            f"{faultLabel(bundle, focus)}. Useful detection changed from "
            f"{focus.clean.detection_fraction:.1%} clean to {focus.worst_metrics.detection_fraction:.1%}; "
            f"{focus.worst_metrics.detected} of {focus.worst_metrics.engines} histories were warned in time. "
            f"Late warnings: {focus.worst_metrics.late}. Missed histories: {focus.worst_metrics.missed}. "
            f"Early-alarm burden changed from {focus.clean.early_alarm_burden:.2%} to "
            f"{focus.worst_metrics.early_alarm_burden:.2%}. "
            "Other cases may have higher alarm burden; check the required scenario metrics in the evidence export as well."
        )
    else:
        faultSummary = "No required fault result is available for comparison."
    ordinary = next((v for v in selection.ranked if v.qualifies and v.candidate == CandidateKind.xgboost), None)
    augmented = next(
        (v for v in selection.ranked if v.qualifies and v.candidate == CandidateKind.xgboost_augmented), None
    )
    if ordinary and augmented:
        meanDelta = 100 * (augmented.mean_detection_required - ordinary.mean_detection_required)
        worstDelta = 100 * (augmented.worst_detection_required - ordinary.worst_detection_required)
        burdenDelta = 100 * (augmented.clean.early_alarm_burden - ordinary.clean.early_alarm_burden)
        augmentation = (
            f"Comparing the strongest qualifying configurations under the selection rule: "
            f"{candidateLabel(ordinary)} and {candidateLabel(augmented)}. With augmentation, mean required-case detection "
            f"changed by {meanDelta:+.2f} percentage points, worst-case detection by {worstDelta:+.2f} percentage points, "
            f"and clean early-alarm burden by {burdenDelta:+.2f} percentage points (lower burden is better). "
        )
        if meanDelta <= 0 and worstDelta <= 0:
            augmentation += "Augmentation did not improve measured mean or worst-case detection in this comparison. "
        else:
            augmentation += "Some measured detection results improved; this does not establish a general benefit. "
        augmentation += "These are selected configurations, not a controlled causal test of augmentation."
    else:
        missing = "ordinary XGBoost" if ordinary is None else "augmented XGBoost"
        if ordinary is None and augmented is None:
            missing = "either XGBoost family"
        augmentation = (
            f"There is no qualifying candidate from {missing}. A comparison between two qualifying "
            "configurations is therefore unavailable; do not conclude that augmentation helped."
        )
    faultLink = comparison + "#fault-results"
    if focus:
        query = urlencode({"candidate": f"{focus.candidate.value}/{focus.config_id}"})
        faultLink = f"{comparison}?{query}#fault-results"
        traces = [s for s in bundle.replay_series if s.candidate == focus.candidate and s.config_id == focus.config_id]
        example = next((s for s in traces if s.fault and s.equipment_id == "13" and bundle.profile.dataset_id == "cmapss-fd001-train"), None)
        example = example or next((s for s in traces if s.fault), traces[0] if traces else None)
        if example:
            replay += "?" + urlencode({"equipment": example.equipment_id, "scenario": example.scenario_id})
    return DecisionReport(
        title=title,
        summary=summary,
        fault_summary=faultSummary,
        augmentation_summary=augmentation,
        unaugmented=ordinary,
        augmented=augmented,
        limitations=[bundle.holdout_status, *bundle.limitations],
        guide=[
            GuideAnswer(
                question="Why was this model selected?",
                answer=summary,
                link=comparison,
                link_label="Inspect candidate results",
            ),
            GuideAnswer(
                question="Which fault caused the biggest problem?",
                answer=faultSummary,
                link=faultLink,
                link_label="Inspect required fault cases",
            ),
            GuideAnswer(
                question="Did augmented training help?",
                answer=augmentation,
                link=comparison + "#augmentation",
                link_label="Compare the configurations",
            ),
            GuideAnswer(
                question="What should I inspect next?",
                answer="Inspect the clean and faulted warning replay, then check missed detections, early alarms and the limitations. A passing development result does not approve deployment.",
                link=replay,
                link_label="Open warning replay",
            ),
        ],
    )
