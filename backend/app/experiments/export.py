"""Portable evidence with no raw uploaded rows."""

import csv
import io
import json
import zipfile
from html import escape

from app.experiments.decision import decision
from app.schemas import EvidenceBundle


def csvText(value: str) -> str:
    # Spreadsheet programs treat these prefixes as formulas.
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def export_zip(bundle: EvidenceBundle) -> bytes:
    # Exports retain score traces without exposing uploaded sensor readings.
    bundle = bundle.model_copy(deep=True)
    for series in bundle.replay_series:
        for point in series.points:
            point.sensor_clean = None
            point.sensor_faulted = None
    for explanation in bundle.explanations:
        for contribution in explanation.contributions:
            contribution.value = None
    report = decision(bundle)
    csvStream = io.StringIO(newline="")
    metrics = ("engines", "detection_fraction", "early_alarm_burden", "median_lead_time")
    writer = csv.writer(csvStream)
    writer.writerow(["candidate", "config_id", "scenario_id", "partition", "required", *metrics])
    for row in bundle.scenario_results:
        values = row.metrics.model_dump(mode="json")
        writer.writerow(
            [
                row.candidate.value,
                csvText(row.config_id),
                csvText(row.scenario_id),
                row.partition.value,
                row.required,
                *[values.get(key) for key in metrics],
            ]
        )
    provenance = {
        "experiment_id": bundle.experiment_id,
        "dataset_id": bundle.dataset_id or bundle.profile.dataset_id,
        "dataset_fingerprint": bundle.profile.data_hash,
        "config_fingerprint": bundle.config_fingerprint,
        "git_commit": bundle.git_commit,
        "source_digest": bundle.source_digest,
        "schema_version": bundle.schema_version,
        "generated_at": bundle.generated_at.isoformat(),
        "confirmed_mapping": bundle.confirmed_mapping.model_dump() if bundle.confirmed_mapping else None,
        "complete_histories_confirmed": bundle.complete_histories_confirmed,
        "holdout_status": bundle.holdout_status,
        "config": bundle.config,
        "raw_sensor_values_included": False,
    }
    paragraphs = "".join(
        f"<p>{escape(text)}</p>" for text in (report.summary, report.fault_summary, report.augmentation_summary)
    )
    limitations = "".join(f"<li>{escape(text)}</li>" for text in report.limitations)
    rows = "".join(
        f"<tr><td>{escape(v.candidate.value + '/' + v.config_id)}</td>"
        f"<td>{v.qualifies}</td><td>{v.clean.detection_fraction:.2%}</td>"
        f"<td>{v.mean_detection_required:.2%}</td><td>{v.worst_detection_required:.2%}</td>"
        f"<td>{v.clean.early_alarm_burden:.2%}</td></tr>"
        for v in bundle.development_selection.ranked
    )
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sidekick decision report</title>
<style>body{{font:16px/1.6 system-ui;max-width:1050px;margin:40px auto;padding:0 20px;color:#18232b}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #ccc;padding:8px}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f6;padding:20px}}.scroll{{overflow:auto}}</style>
<h1>Sidekick decision report</h1><p>{escape(bundle.profile.source)}</p><h2>{escape(report.title)}</h2>
{paragraphs}<div class="scroll"><table><thead><tr><th>Configuration</th><th>Qualified</th><th>Clean detection</th>
<th>Mean required detection</th><th>Worst required detection</th><th>Clean alarm burden</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>How to read these results</h2><p>Detection counts equipment with a useful warning 10 to 30 cycles before failure.
Early-alarm burden is the fraction of eligible healthy cycles spent in an alert, beyond 45 cycles before failure.
Warning time is measured in operating cycles, not hours.</p><h2>Limitations</h2><ul>{limitations}</ul>
<h2>Source and configuration</h2><pre>{escape(json.dumps(provenance, indent=2))}</pre>
<p>This export excludes the raw uploaded CSV. JSON evidence contains derived metrics and selected model-score replay traces.</p></html>"""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("decision-report.html", html)
        archive.writestr("evidence.json", bundle.model_dump_json(indent=2))
        archive.writestr("metrics.csv", csvStream.getvalue())
        archive.writestr("provenance.json", json.dumps(provenance, indent=2))
    return stream.getvalue()
