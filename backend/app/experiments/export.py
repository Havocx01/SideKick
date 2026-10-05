"""Portable evidence with no raw uploaded rows."""

import csv
import io
import json
import zipfile
from html import escape

from app.experiments.decision import candidateLabel, decision, percentage
from app.schemas import EvidenceBundle, Partition


def csvText(value: str) -> str:
    # Spreadsheet programs treat these prefixes as formulas.
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def export_zip(bundle: EvidenceBundle, candidate=None, partition=Partition.out_of_fold) -> bytes:
    # Exports retain score traces without exposing uploaded sensor readings.
    bundle = bundle.model_copy(deep=True)
    for series in bundle.replay_series:
        for point in series.points:
            point.sensor_clean = None
            point.sensor_faulted = None
    for explanation in bundle.explanations:
        for contribution in explanation.contributions:
            contribution.value = None
    csvStream = io.StringIO(newline="")
    metrics = ("engines", "detected", "late", "missed", "detection_fraction", "early_alarm_burden", "eligible_cycles", "median_lead_time")
    writer = csv.writer(csvStream)
    writer.writerow(["candidate", "config_id", "scenario_id", "partition", "required", "expected_engines", "coverage_complete", *metrics])
    for row in bundle.scenario_results:
        values = row.metrics.model_dump(mode="json")
        writer.writerow(
            [
                row.candidate.value,
                csvText(row.config_id),
                csvText(row.scenario_id),
                row.partition.value,
                row.required,
                row.expected_engines,
                row.coverage_complete,
                *[values.get(key) for key in metrics],
            ]
        )
    html, provenance = render_report(bundle, candidate, partition)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("decision-report.html", html)
        archive.writestr("evidence.json", bundle.model_dump_json(indent=2))
        archive.writestr("metrics.csv", csvStream.getvalue())
        archive.writestr("provenance.json", json.dumps(provenance, indent=2))
    return stream.getvalue()


def render_report(bundle: EvidenceBundle, candidate=None, partition=Partition.out_of_fold):
    report = decision(bundle, candidate, partition)
    provenance = {
        "experiment_id": bundle.experiment_id,
        "dataset_id": bundle.dataset_id or bundle.profile.dataset_id,
        "dataset_fingerprint": bundle.profile.data_hash,
        "config_fingerprint": bundle.config_fingerprint,
        "git_commit": bundle.git_commit,
        "source_digest": bundle.source_digest,
        "dependency_versions": bundle.dependency_versions,
        "schema_version": bundle.schema_version,
        "generated_at": bundle.generated_at.isoformat(),
        "confirmed_mapping": bundle.confirmed_mapping.model_dump() if bundle.confirmed_mapping else None,
        "complete_histories_confirmed": bundle.complete_histories_confirmed,
        "holdout_status": bundle.holdout_status,
        "config": bundle.config,
        "report_candidate": report.inspected_candidate,
        "report_partition": partition.value,
        "protocol": bundle.protocol.model_dump(mode="json") if bundle.protocol else None,
        "pilot_brief": bundle.pilot_brief.model_dump(mode="json") if bundle.pilot_brief else None,
        "frozen_model": bundle.frozen_model.model_dump(mode="json") if bundle.frozen_model else None,
        "validation": bundle.validation.model_dump(mode="json") if bundle.validation else None,
        "raw_sensor_values_included": False,
    }
    paragraphs = "".join(
        f"<p>{escape(text)}</p>" for text in (report.summary, report.fault_summary, report.augmentation_summary)
    )
    limitations = "".join(f"<li>{escape(text)}</li>" for text in report.limitations)
    rows = "".join(
        f"<tr><td>{escape(candidateLabel(v))}</td>"
        f"<td>{v.qualifies}</td><td>{v.clean.detection_fraction:.2%}</td>"
        f"<td>{v.mean_detection_required:.2%}</td><td>{v.worst_detection_required:.2%}</td>"
        f"<td>{percentage(v.clean.early_alarm_burden)}</td><td>{percentage(v.worst_burden_required)}</td>"
        f"<td>{'Unknown (historical)' if v.coverage_complete is None else str(v.coverage_complete)}</td></tr>"
        for v in (bundle.final_evaluation if partition == Partition.holdout else bundle.development_selection).ranked
    )
    def delta(value):
        return f"{value * 100:+.3f}" if value is not None else "Unavailable"

    def interval(values):
        return "[" + ", ".join(delta(v) for v in values) + "]" if values else "Unavailable"

    paired = "".join(f"<tr><td>{escape(p.first)} to {escape(p.second)}</td><td>{escape(p.kind)}</td>"
                     f"<td>{delta(p.detection_delta)}</td><td>{interval(p.detection_interval)}</td>"
                     f"<td>{delta(p.burden_delta)}</td><td>{interval(p.burden_interval)}</td></tr>" for p in bundle.paired_comparisons)
    final = bundle.final_evaluation
    final_html = "<p>No completed final validation is attached.</p>"
    if final and final.ranked:
        selected = final.ranked[0]
        final_html = f"<p>{escape(candidateLabel(selected))}: {'meets' if selected.qualifies else 'does not meet'} final criteria. Clean detection {selected.clean.detection_fraction:.2%}; worst required detection {selected.worst_detection_required:.2%}; highest required burden {percentage(selected.worst_burden_required)}. Histories are now exposed.</p>"
    criteria = bundle.development_selection.criteria
    boundary = bundle.config.get("transition_band_end", 45)
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sidekick decision report</title>
<style>body{{font:16px/1.6 system-ui;max-width:1050px;margin:40px auto;padding:0 20px;color:#18232b}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #ccc;padding:8px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f6;padding:20px}}.scroll{{overflow:auto}}</style>
<h1>Sidekick v1.5 decision report</h1><p>{escape(bundle.profile.source)} · {escape(partition.value)}</p><h2>{escape(report.title)}</h2>
{paragraphs}<div class="scroll"><table><thead><tr><th>Configuration</th><th>Qualified</th><th>Clean detection</th>
<th>Mean required detection</th><th>Worst required detection</th><th>Clean burden</th><th>Highest required burden</th><th>Complete coverage</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Final validation</h2>{final_html}
<h2>Exploratory paired development comparisons</h2><p>95% paired equipment bootstrap intervals. These comparisons are conditional on development selection and do not prove a causal or field benefit.</p>
<p>Changes are second configuration minus first, in percentage points. Higher detection and lower burden are better.</p>
<div class="scroll"><table><thead><tr><th>Configurations</th><th>Comparison</th><th>Mean required detection change</th><th>95% interval</th><th>Mean required burden change</th><th>95% interval</th></tr></thead><tbody>{paired}</tbody></table></div>
<h2>How to read these results</h2><p>Warnings in time (detection) counts equipment histories with an alert active {criteria.min_useful_lead} to {criteria.horizon_cycles} cycles before documented failure.
Warnings too late means no warning was active in the useful window, but one was active in the late window before failure. A missed warning window means neither a useful nor a late warning was recorded. Earlier alerts may still have occurred in either case.</p>
<p>Time spent warning too early (early-alarm burden) is the fraction of eligible cycles spent in an alert, beyond {boundary} cycles before failure. It is not the probability that an individual warning is false. Unavailable burden cannot pass.
Warning time is measured in operating cycles, not necessarily hours or minutes.</p><h2>Limitations</h2><ul>{limitations}</ul>
<h2>Source and configuration</h2><pre>{escape(json.dumps(provenance, indent=2))}</pre>
<p>This export excludes the raw uploaded CSV. JSON evidence contains derived metrics and selected model-score replay traces.</p></html>"""
    return html, provenance
