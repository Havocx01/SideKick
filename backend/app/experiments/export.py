"""Portable evidence with no raw uploaded rows."""

import csv
import io
import json
import zipfile

from app.experiments.decision import decision
from app.experiments.decision_document import render_decision_document
from app.experiments.pilot import validate_saved_record
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
        if bundle.pilot_review:
            archive.writestr("pilot-review.json", bundle.pilot_review.model_dump_json(indent=2))
    return stream.getvalue()


def render_report(bundle: EvidenceBundle, candidate=None, partition=Partition.out_of_fold):
    validate_saved_record(bundle)
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
        "pilot_review": bundle.pilot_review.model_dump(mode="json") if bundle.pilot_review else None,
        "frozen_model": bundle.frozen_model.model_dump(mode="json") if bundle.frozen_model else None,
        "validation": bundle.validation.model_dump(mode="json") if bundle.validation else None,
        "raw_sensor_values_included": False,
    }
    return render_decision_document(bundle, report, provenance, partition), provenance
