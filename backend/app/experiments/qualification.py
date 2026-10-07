"""Explain the recorded verdict without changing the selection rule."""

from app.schemas import AcceptanceCriteria, CandidateVerdict, EvidenceBundle, Partition


def qualification_reason(bundle: EvidenceBundle, verdict: CandidateVerdict,
                         criteria: AcceptanceCriteria, partition: Partition) -> str:
    if verdict.qualifies:
        return (f"Healthy sensors and all {verdict.required_scenarios} required faults met "
                "the detection and early-alarm limits.")

    rows = [row for row in bundle.scenario_results if row.candidate == verdict.candidate
            and row.config_id == verdict.config_id and row.partition == partition and row.required and row.fault]

    def label(scenario_id):
        row = next((row for row in rows if row.scenario_id == scenario_id), None)
        return row.fault.label() if row else scenario_id or "Required fault cases"

    reasons = []

    def measured(value, limit):
        text = f"{value:.2%}"
        return f"about {text}" if text == f"{limit:.2%}" else text

    def detection(context, metrics, fraction):
        if fraction < criteria.min_detection_fraction:
            count = f"{metrics.detected}/{metrics.engines} warned in time " if metrics else ""
            reasons.append(f"{context}: {count}({measured(fraction, criteria.min_detection_fraction)}), below the {criteria.min_detection_fraction:.1%} minimum.")

    def burden(context, value):
        if value is None:
            reasons.append(f"{context}: early alarm time is unavailable, so this case cannot pass.")
        elif value > criteria.max_early_alarm_burden:
            reasons.append(f"{context}: {measured(value, criteria.max_early_alarm_burden)} early alarm time, above the {criteria.max_early_alarm_burden:.1%} maximum.")

    detection("Healthy sensors", verdict.clean, verdict.clean.detection_fraction)
    burden("Healthy sensors", verdict.clean.early_alarm_burden)
    if verdict.required_scenarios:
        detection(label(verdict.worst_scenario_id), verdict.worst_metrics, verdict.worst_detection_required)
        # Highest burden can belong to a different case from lowest detection.
        if verdict.worst_burden_required is not None:
            burden_id = verdict.worst_burden_scenario_id
            if burden_id is None:
                matching = next((row for row in rows if row.metrics.early_alarm_burden == verdict.worst_burden_required), None)
                burden_id = matching.scenario_id if matching else None
            burden(label(burden_id), verdict.worst_burden_required)
        else:
            # Older bundles may lack the aggregate; use their recorded cases.
            known = [row for row in rows if row.metrics.early_alarm_burden is not None]
            if known:
                highest = max(known, key=lambda row: row.metrics.early_alarm_burden)
                burden(label(highest.scenario_id), highest.metrics.early_alarm_burden)
        unavailable = next((row for row in rows if row.metrics.early_alarm_burden is None), None)
        if unavailable:
            burden(label(unavailable.scenario_id), None)
    else:
        reasons.append("No required fault cases were evaluated.")
    if verdict.coverage_complete is False:
        reasons.append("Required fault cases did not cover all expected histories.")
    return " ".join(reasons) or "Some required fault cases could not be assessed. Inspect their recorded metrics."
