"""Portable review drafts containing derived evidence, never uploaded sensor rows."""
import html
import io
import json
import time
import zipfile

from app import __version__

PARTITIONS = {"out_of_fold": "Development", "holdout": "Final validation"}


def stamp(value):
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(value)) if value else "Not saved"


def export_brief(record):
    result = record.result
    e = html.escape
    title = e(result.title if result else "Analysis")
    text = record.brief_text or (result.brief_draft or result.summary if result else "")
    context = record.context
    rows = [("Experiment", context.experiment_id or "Recorded benchmark"), ("Evaluation", PARTITIONS.get(context.partition.value, context.partition.value)),
            ("Models", ", ".join(context.candidates)), ("Analysis", record.id), ("Draft saved", stamp(record.brief_saved_at))]
    if context.scenario_id:
        rows.append(("Scenario", context.scenario_id))
    if context.equipment_id:
        rows.append(("History", context.equipment_id))
    if context.cycle is not None:
        rows.append(("Cycle", str(context.cycle)))
    if context.dataset_id:
        rows.append(("Dataset", context.dataset_id))
    sections = ""
    if result:
        rows += [("Mode", "AI investigation" if result.mode == "ai" else "Recorded evidence analysis"), ("Provider model", result.model or "None"),
                 ("Prompt version", result.prompt_version), ("Evidence digest", result.evidence_digest), ("Verification", result.verification)]
        if result.fallback_reason:
            rows.append(("Fallback", result.fallback_reason))
        findings = "".join(f"<li><strong>{e(f.title)}</strong>: {e(f.detail)}</li>" for f in result.findings)
        sources = "".join(f'<li id="{e(s.id)}">{e(s.label)}: {e(s.display)} <small>({e(s.context)}; reference {e(s.id)}, metric {e(s.metric)}, unit {e(s.unit)})</small></li>' for s in result.sources)
        actions = "".join(f"<li><strong>{e(a.label)}</strong>: {e(a.detail)}</li>" for a in result.actions)
        limits = "".join(f"<li>{e(item)}</li>" for item in result.limitations)
        interpretation = f"<h2>AI interpretation</h2><p class=note>Generated text. Verify it against the evidence below.</p><p>{e(result.interpretation)}</p>" if result.interpretation else ""
        assessment = "".join(f"<li>{e(claim.text)} <small>[{e(', '.join(claim.source_ids))}]</small></li>" for claim in result.assessment)
        trace = "".join(f"<li>{e(call.label)} <small>[{e(', '.join(call.source_ids))}]</small></li>" for call in result.investigation)
        sections = f"{interpretation}<h2>Assessment</h2><ul>{assessment}</ul><h2>Findings</h2><ul>{findings}</ul><h2>Evidence</h2><ul>{sources}</ul><h2>Proposed next checks</h2><ul>{actions or '<li>Agree a next check with the equipment engineer.</li>'}</ul><h2>Limitations</h2><ul>{limits}</ul><h2>Investigation record</h2><ul>{trace}</ul>"
    meta = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in rows)
    document = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title>'
                '<style>body{font:16px/1.6 system-ui;max-width:850px;margin:40px auto;padding:24px}pre{white-space:pre-wrap;font:inherit}'
                'table{border-collapse:collapse}th,td{text-align:left;padding:2px 12px 2px 0;vertical-align:top}th{font-weight:500}.note,small{color:#555}</style>'
                f'<h1>{title}</h1><p class=note>Engineer review draft. Original metrics and qualification are unchanged; this is not a pilot decision or deployment approval.</p>'
                f'<table>{meta}</table><h2>Review draft</h2><pre>{e(text)}</pre>{sections}'
                f'<p class=note>Sidekick {e(__version__)}. Raw uploaded data are excluded.</p></html>')
    payload = {"sidekick_version": __version__, "kind": "engineer_review_draft", "analysis": json.loads(record.model_dump_json())}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("review-brief.html", document)
        archive.writestr("analysis.json", json.dumps(payload, indent=2))
    return output.getvalue()
