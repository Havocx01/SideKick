"""Standalone engineering report. Every result comes from the selected evidence scope."""

import json
from html import escape

from app import __version__
from app.experiments.decision import candidateLabel, faultLabel
from app.experiments.pilot_report import pilot_html
from app.schemas import Partition


STYLE = """
:root{color-scheme:light;--ink:#1d1d1f;--muted:#60646c;--line:#dfe2e7;--paper:#fff;--wash:#f5f6f8;--blue:#0066cc}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:15px/1.65 system-ui,sans-serif}
.document{max-width:1160px;margin:32px auto;padding:40px 48px;background:var(--paper);border:1px solid var(--line);border-radius:12px}
header{display:flex;justify-content:space-between;align-items:start;gap:24px;border-bottom:1px solid var(--line);padding-bottom:24px}
h1{font-size:30px;line-height:1.2;letter-spacing:-.025em;margin:8px 0 12px}h2{font-size:20px;line-height:1.3;margin:0 0 16px}h3{font-size:16px;margin:0 0 8px}
p{margin:8px 0 16px;max-width:80ch}.brand{font-size:18px;font-weight:600}.brand span{color:var(--blue)}.muted,small{color:var(--muted)}
section{margin-top:32px}section+section{padding-top:28px;border-top:1px solid var(--line)}
.disposition{border:1px solid var(--line);border-radius:10px;padding:24px;background:var(--wash)}.disposition h2{font-size:24px;margin:8px 0 12px}
.status{font-weight:600}.status.pass{color:#146c37}.status.fail{color:#aa2424}.status.pending{color:var(--blue)}
.facts,.pilot-context{display:grid;grid-template-columns:minmax(160px,1fr) minmax(0,2fr);gap:10px 24px;margin:0}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.facts dd,.pilot-context dd{white-space:pre-wrap}
.split{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:32px}.split>div{min-width:0}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px 10px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--muted)}tbody th{color:var(--ink);font-weight:400}td{font-variant-numeric:tabular-nums}caption{text-align:left;margin-bottom:12px;font-weight:600}
.outcomes td:not(:first-child){text-align:right;white-space:nowrap}.outcomes thead th:not(:first-child){text-align:right}
.key-results{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0 0;padding-top:16px;border-top:1px solid var(--line)}.key-results dd{font-size:20px;font-weight:600}.key-results dt{font-size:13px}
ul,ol{padding-left:22px;margin:12px 0}li+li{margin-top:10px}.risk{margin-top:20px}.risk p{color:var(--muted);margin-bottom:6px}
.identifier{font:12px/1.65 ui-monospace,monospace;overflow-wrap:anywhere}pre{font:12px/1.65 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:var(--wash);padding:20px;border-radius:8px}
details{border:1px solid var(--line);border-radius:8px;padding:16px;margin-top:20px}summary{cursor:pointer;font-weight:600}details[open]>summary{margin-bottom:16px}
.print-button{font:inherit;font-size:14px;white-space:nowrap;cursor:pointer;border:1px solid var(--line);border-radius:8px;padding:9px 14px;background:var(--paper);color:var(--ink)}
.print-button:hover,.print-button:focus-visible{background:var(--wash)}footer{margin-top:32px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
.sign-off{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;margin-top:20px}.sign-off span{display:block;border-bottom:1px solid var(--line);padding-bottom:28px;color:var(--muted)}
@media(max-width:760px){.document{margin:0;padding:24px 20px;border:0;border-radius:0}.split,.sign-off{grid-template-columns:minmax(0,1fr)}.key-results{grid-template-columns:repeat(2,minmax(0,1fr))}.facts,.pilot-context{grid-template-columns:minmax(0,1fr);gap:4px}.facts dd,.pilot-context dd{margin-bottom:12px}header{flex-wrap:wrap}h1{font-size:26px}}
@media print{@page{margin:15mm}body{background:white;font-size:11px}.document{margin:0;padding:0;border:0;max-width:none}.print-button{display:none}h1{font-size:24px}h2{font-size:16px}section{margin-top:20px}h2,h3,summary{break-after:avoid}tr,.risk,.disposition{break-inside:avoid}thead{display:table-header-group}.scroll{overflow:visible}table{font-size:10px}th,td{padding:7px 5px}.split{grid-template-columns:minmax(0,1fr)}details::details-content{content-visibility:visible;height:auto}details>*:not(summary){display:block}pre{font-size:9px}.sign-off{grid-template-columns:repeat(3,minmax(0,1fr))}}
"""


def text(value):
    return escape(str(value)) if value is not None else "Not recorded"


def percent(value, digits=2):
    return f"{value:.{digits}%}" if value is not None else "Unavailable"


def facts(items):
    return '<dl class="facts">' + "".join(f"<dt>{text(label)}</dt><dd>{text(value)}</dd>" for label, value in items) + "</dl>"


def table(headers, rows, caption=None, class_name=""):
    heading = "".join(f'<th scope="col">{text(label)}</th>' for label in headers)
    body = "".join("<tr>" + "".join(f"<td>{text(value)}</td>" for value in row) + "</tr>" for row in rows)
    label = f"<caption>{text(caption)}</caption>" if caption else ""
    return f'<div class="scroll"><table class="{class_name}">{label}<thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table></div>'


def render_decision_document(bundle, report, provenance, partition):
    selection = bundle.final_evaluation if partition == Partition.holdout else bundle.development_selection
    focus = next((item for item in selection.ranked if f"{item.candidate.value}/{item.config_id}" == report.inspected_candidate), None)
    criteria = selection.criteria
    stage = "Final validation" if partition == Partition.holdout else "Development evaluation"
    historical = not bundle.experiment_id or "historical" in bundle.holdout_status.lower()
    if not focus or not focus.qualifies:
        disposition, tone = "Revise before further evaluation", "fail"
        next_step = "Review the failed or missing results. Correct the data, model or fault protocol, then rerun development evaluation before proposing a site trial."
    elif partition == Partition.holdout:
        disposition, tone = "Site review required", "pass"
        next_step = "The recorded final test meets its limits. The equipment engineer must review relevance, operational consequences and remaining risks before considering a supervised site trial."
    else:
        disposition, tone = "Fresh validation required", "pending"
        next_step = "The candidate meets development limits. Agree the equipment scope and fault protocol, freeze the selected model and threshold, then evaluate on untouched equipment histories."
    recommendation = candidateLabel(selection.recommended) if selection.recommended else "None. No configuration qualifies in this partition."
    summary = f'<p>{text(report.qualification_reason)}</p><p>{text(next_step)}</p>'
    freshness = "Previously examined histories. These results are not fresh independent validation." if historical else bundle.holdout_status
    context = facts([
        ("Inspected configuration", candidateLabel(focus) if focus else "No candidate results"),
        ("Recommended configuration", recommendation),
        ("Evaluation", stage), ("Equipment family", (bundle.pilot_review.agreement.brief if bundle.pilot_review else bundle.pilot_brief).equipment_family if bundle.pilot_review or bundle.pilot_brief else None),
        ("Data source", bundle.profile.source), ("Evidence recorded", bundle.generated_at.strftime("%d %b %Y, %H:%M %z")),
    ])
    limits = facts([
        ("Minimum in-time warnings", percent(criteria.min_detection_fraction, 1)),
        ("Maximum early alarm time", percent(criteria.max_early_alarm_burden, 1)),
        ("Useful warning window", f"{criteria.min_useful_lead} to {criteria.horizon_cycles} operating cycles before failure"),
        ("Required fault cases passed", f"{focus.required_passed} / {focus.required_scenarios}" if focus else "Unavailable"),
        ("Complete required coverage", "Unavailable" if not focus else "Unknown (historical)" if focus.coverage_complete is None else "Yes" if focus.coverage_complete else "No"),
    ])
    scope = facts([
        ("Data histories", bundle.profile.equipment_count), ("Development histories", len(bundle.splits.development)),
        ("Reserved histories", len(bundle.splits.holdout)), ("Validation folds", len(bundle.splits.folds)),
        ("Alert threshold", f"{focus.threshold:.6g} (model score)" if focus else "Unavailable"),
        ("Alert opens / closes", f"{bundle.config.get('alert_on_consecutive', 'Not recorded')} / {bundle.config.get('alert_off_consecutive', 'Not recorded')} consecutive scores"),
    ])
    outcomes = "<p>No candidate metrics are available.</p>"
    key_results = ""
    risks = ""
    scenario_rows = []
    if focus:
        clean, worst = focus.clean, focus.worst_metrics
        def outcome_values(metrics):
            if metrics is None:
                return ["Unavailable"] * 6
            return [f"{metrics.detected} / {metrics.engines}", metrics.late, metrics.missed,
                    percent(metrics.early_alarm_burden),
                    f"{percent(metrics.detection_ci.lower)} to {percent(metrics.detection_ci.upper)}",
                    f"{metrics.median_lead_time:g} cycles" if metrics.median_lead_time is not None else "Unavailable"]
        labels = ["Warned in time", "Warned late", "Missed both windows", "Early alarm time", "95% detection interval", "Median warning lead"]
        outcomes = table(["Measure", "Healthy sensors", "Lowest detection fault"],
                         [[label, left, right] for label, left, right in zip(labels, outcome_values(clean), outcome_values(worst))], class_name="outcomes")
        matching = [row for row in bundle.scenario_results if row.candidate == focus.candidate and row.config_id == focus.config_id and row.partition == partition]
        required = [row for row in matching if row.required and row.fault]
        burden = next((row for row in required if row.scenario_id == focus.worst_burden_scenario_id), None)
        if burden is None:
            known = [row for row in required if row.metrics.early_alarm_burden is not None]
            burden = max(known, key=lambda row: row.metrics.early_alarm_burden) if known else None
        detection_detail = (f"{worst.detected} / {worst.engines} histories warned in time; {worst.late} late and {worst.missed} missed both windows. "
                            f"Detection {percent(worst.detection_fraction)} against the {percent(criteria.min_detection_fraction, 1)} minimum.") if worst else "Scenario measurements are unavailable."
        risks = f'<article class="risk"><h3>Lowest detection case</h3><p>{text(faultLabel(bundle, focus, partition))}</p><p>{text(detection_detail)}</p><small class="identifier">{text(focus.worst_scenario_id)}</small></article>'
        burden_value = burden.metrics.early_alarm_burden if burden else focus.worst_burden_required
        key_results = '<dl class="key-results">' + "".join(f'<div><dt>{text(label)}</dt><dd>{text(value)}</dd></div>' for label, value in [
            ("Healthy warnings in time", f"{clean.detected} / {clean.engines}"),
            ("Weakest fault warnings", f"{worst.detected} / {worst.engines}" if worst else "Unavailable"),
            ("Required cases passed", f"{focus.required_passed} / {focus.required_scenarios}"),
            ("Highest fault alarm time", percent(burden_value)),
        ]) + '</dl>'
        burden_label = burden.fault.label() if burden and burden.fault else focus.worst_burden_scenario_id
        burden_detail = (f"{percent(burden_value)} of eligible early cycles in alarm against the {percent(criteria.max_early_alarm_burden, 1)} maximum. "
                         "This may differ from the lowest-detection case.") if burden_value is not None else "Alarm time is unavailable. It cannot establish a passing result."
        risks += f'<article class="risk"><h3>Highest early alarm case</h3><p>{text(burden_label)}</p><p>{text(burden_detail)}</p><small class="identifier">{text(burden.scenario_id if burden else focus.worst_burden_scenario_id)}</small></article>'
        for row in matching:
            if row.fault is None:
                continue
            metrics = row.metrics
            issues = []
            if metrics.detection_fraction < criteria.min_detection_fraction:
                issues.append("Detection below minimum")
            if metrics.early_alarm_burden is None:
                issues.append("Alarm time unavailable")
            elif metrics.early_alarm_burden > criteria.max_early_alarm_burden:
                issues.append("Alarm time above maximum")
            if row.coverage_complete is False or (row.expected_engines is not None and metrics.engines != row.expected_engines):
                issues.append("Incomplete coverage")
            scenario_rows.append([row.fault.label(), "Required" if row.required else "Supplemental",
                                  f"{metrics.detected} / {metrics.engines}", metrics.late, metrics.missed,
                                  percent(metrics.early_alarm_burden), "; ".join(issues) or "Meets recorded limits"])
    final = bundle.final_evaluation
    final_text = "No completed final validation is attached. Development results alone cannot support a site-use decision."
    if final and final.ranked:
        tested = final.ranked[0]
        final_text = (f"{candidateLabel(tested)} {'meets' if tested.qualifies else 'does not meet'} recorded final limits. "
                      f"Healthy warnings in time: {tested.clean.detected} / {tested.clean.engines}. "
                      f"Weakest required detection: {percent(tested.worst_detection_required)}. "
                      f"Highest required early alarm time: {percent(tested.worst_burden_required)}. "
                      "These histories are now exposed and must not be reused as a fresh validation set.")
    final_section = f'<p>{text(final_text)}</p><p class="muted">{text(freshness)}</p>'
    source_rows = facts([(label, provenance[key]) for label, key in [
        ("Experiment ID", "experiment_id"), ("Dataset ID", "dataset_id"), ("Dataset fingerprint", "dataset_fingerprint"),
        ("Experiment fingerprint", "config_fingerprint"), ("Git commit", "git_commit"), ("Source digest", "source_digest"),
        ("Evidence schema", "schema_version")]])
    configs = next((item for item in bundle.candidates if focus and item.candidate == focus.candidate and item.config_id == focus.config_id), None)
    configuration = escape(json.dumps({"candidate_parameters": configs.params if configs else None, "experiment_config": bundle.config,
                                       "confirmed_mapping": provenance["confirmed_mapping"], "protocol": provenance["protocol"]}, indent=2))
    ranking = table(["Configuration", "Meets limits", "Healthy detection", "Mean fault detection", "Weakest fault detection", "Highest fault alarm time", "Coverage"], [
        [candidateLabel(item), "Yes" if item.qualifies else "No", percent(item.clean.detection_fraction),
         percent(item.mean_detection_required), percent(item.worst_detection_required), percent(item.worst_burden_required),
         "Unknown (historical)" if item.coverage_complete is None else "Complete" if item.coverage_complete else "Incomplete"] for item in selection.ranked])
    fault_table = table(["Case", "Role", "In time", "Late", "Missed", "Early alarm time", "Result"], scenario_rows) if scenario_rows else "<p>No scenario-level evidence is stored for this model and partition.</p>"
    def change(value):
        return f"{value * 100:+.3f}" if value is not None else "Unavailable"
    def interval(values):
        return " to ".join(change(value) for value in values) if values else "Unavailable"
    paired = table(["Configurations", "Comparison", "Detection change (pp)", "95% interval", "Burden change (pp)", "95% interval"], [
        [f"{item.first} to {item.second}", item.kind, change(item.detection_delta), interval(item.detection_interval), change(item.burden_delta), interval(item.burden_interval)] for item in bundle.paired_comparisons]) if bundle.paired_comparisons else "<p>No paired configuration comparison is recorded.</p>"
    limitations = "".join(f"<li>{text(item)}</li>" for item in dict.fromkeys(report.limitations))
    review = bundle.pilot_review.outcome if bundle.pilot_review else None
    review_status = (f"Recorded for {bundle.pilot_review.agreement.candidate} in final validation by {review.reviewing_engineer}. "
                     "See the engineering pilot section for the decision and conditions. This review does not approve other configurations or evaluations.") if review else "Not recorded. This document contains test evidence, not an engineer-approved decision."
    boundary = bundle.config.get("transition_band_end", 45)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sidekick decision report | {text(candidateLabel(focus) if focus else 'No candidate')}</title><style>{STYLE}</style></head><body><main class="document">
<header><div><div class="brand">Side<span>kick</span></div><h1>Engineering decision report</h1><p class="muted">{text(stage)} · {text(bundle.profile.source)}</p></div><button class="print-button" onclick="window.print()">Print / Save PDF</button></header>
<section class="disposition"><div class="status {tone}">Engineering disposition</div><h2>{text(disposition)}</h2><h3>{text(report.title)}</h3>{summary}{key_results}<p class="muted">This is a test-based recommendation for review, not deployment approval.</p></section>
<section><h2>Decision scope</h2>{context}</section>
<section class="split"><div><h2>Measured outcomes</h2>{outcomes}</div><div><h2>Acceptance limits</h2>{limits}<p class="muted">Healthy readings and every required fault case must pass. Supplemental cases do not qualify the model. These limits are demonstration settings unless agreed in the pilot protocol.</p></div></section>
<section><h2>Critical fault cases</h2>{risks or '<p>No candidate fault evidence is available.</p>'}</section>
<section><h2>Validation and readiness</h2>{final_section}{scope}</section>
<section><h2>Recommended next checks</h2><ol><li>{text(next_step)}</li><li>Verify failure labels, column mapping and separation of equipment across training and evaluation.</li><li>Inspect missed or late histories and alarm time in the required cases. Stored replays are representative examples, not the entire fleet.</li><li>Agree an operational warning response, acceptable alarm workload and validation criteria with the equipment engineer before any supervised trial.</li></ol></section>
<section>{pilot_html(bundle)}<h3>Engineer sign-off</h3><p>{text(review_status)}</p>{'' if review else '<p class="muted">For a printed review only. Complete and retain this sign-off through your engineering process.</p><div class="sign-off"><span>Reviewer / role</span><span>Decision / conditions</span><span>Date / signature</span></div>'}</section>
<section><h2>What this evidence does not establish</h2><ul>{limitations}</ul><p>Site performance, maintenance savings and deployment safety require separate evidence and authorization.</p></section>
<section><h2>Required fault evidence</h2><p>Scoped to {text(report.inspected_candidate)} · {text(stage)}. All stored cases for this scope are listed below; supplemental cases are marked separately.</p><details><summary>Scenario metrics ({len(scenario_rows)} stored cases)</summary>{fault_table}</details></section>
<section><h2>Candidate comparison</h2><p>{text(report.augmentation_summary)}</p>{ranking}<details><summary>Exploratory paired development comparisons</summary><p>Second configuration minus first, in percentage points. Higher detection and lower alarm time are better. 95% paired equipment bootstrap intervals are conditional on development selection and do not prove a causal or field benefit.</p>{paired}</details></section>
<section><h2>Measurement definitions</h2><p>Warnings in time: an alert active {criteria.min_useful_lead} to {criteria.horizon_cycles} operating cycles before documented failure. A late warning has no alert in that window but one in the late window. A missed warning has neither. Earlier alerts can occur in either case.</p><p>Early alarm time is the share of eligible operating cycles spent in alarm beyond {text(boundary)} cycles before failure, not the probability that a warning is false. Unavailable alarm time cannot pass. Cycles are reading intervals, not necessarily hours or minutes. Detection intervals quantify sample uncertainty; they do not certify field reliability. Alert thresholds apply to model scores, not an established probability of equipment failure.</p></section>
<section><h2>Traceability and configuration</h2>{source_rows}<details><summary>Model parameters and test configuration</summary><pre>{configuration}</pre></details><details><summary>Complete provenance record</summary><pre>{text(json.dumps(provenance, indent=2))}</pre></details></section>
<footer>Sidekick {text(__version__)} · Raw uploaded CSV and sensor readings are excluded. The ZIP includes JSON evidence, CSV metrics and provenance. Keep the report with these files for review.</footer>
</main></body></html>'''
