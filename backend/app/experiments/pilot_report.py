"""Readable, escaped pilot context alongside the experiment's numeric evidence."""

from html import escape

from app.experiments.pilot import DECISIONS


def rows_html(rows):
    return '<dl class="pilot-context">' + "".join(f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>" for label, value in rows) + "</dl>"


def pilot_html(bundle):
    pilot = bundle.pilot_review
    brief = pilot.agreement.brief if pilot else bundle.pilot_brief
    if not brief:
        return "<h2>Engineering pilot</h2><p>No pilot agreement or engineer review is recorded.</p>"
    rows = [("Equipment family", brief.equipment_family), ("Reviewing engineer", brief.reviewing_engineer),
            ("Data classification (user declared)", brief.data_classification),
            ("Current procedure", brief.current_procedure), ("Intended decision", brief.intended_decision),
            ("Success measure", brief.success_measure)]
    html = "<h2>Engineering pilot</h2>" + rows_html([(key, value or "Not recorded") for key, value in rows])
    if not pilot:
        return html + "<p>This brief records intentions. No agreed test or measured benefit is attached.</p>"
    agreement = pilot.agreement
    html += rows_html([("Agreed model", agreement.candidate), ("Agreement ID", agreement.agreement_id),
                       ("Dataset fingerprint", agreement.data_hash), ("Protocol fingerprint", agreement.config_fingerprint)])
    html += "<p>Equipment scope, failure labels, representativeness and the protocol were confirmed by the named reviewer before reserved scoring. These are user declarations, not independent verification.</p>"
    if bundle.protocol:
        protocol = bundle.protocol
        html += f"<p>Useful warning window: {protocol.min_useful_lead} to {protocol.horizon_cycles} operating cycles before failure. Minimum detection: {protocol.min_detection_fraction:.1%}. Maximum early-alarm burden: {protocol.max_early_alarm_burden:.1%}.</p>"
        html += "<details><summary>Agreed sensor faults</summary><ul>" + "".join(
            f"<li>{escape(case.fault.label())}: {'required' if case.required else 'supplemental'}</li>" for case in protocol.scenarios) + "</ul></details>"
    review = pilot.outcome
    html += "<h3>Engineer review</h3>"
    if not review:
        return html + "<p>No final engineer decision has been recorded.</p>"
    html += rows_html([("Reviewer", review.reviewing_engineer), ("Next action", DECISIONS[review.decision]),
        ("Decision changed (self-reported)", "Yes" if review.decision_changed else "No"),
        ("Reason and observations", review.observations), ("Reserved evaluation met limits", "Yes" if review.final_qualifies else "No"),
        ("Validation ID", review.validation_id), ("Frozen model digest", review.artifact_digest)])
    if review.review_minutes_saved is not None:
        html += rows_html([("Current procedure review (minutes)", review.baseline_review_minutes),
            ("Sidekick review (minutes)", review.sidekick_review_minutes),
            ("Reported minutes saved", review.review_minutes_saved)])
    html += "<p>Review decisions and timings are self-reported. A timing difference does not establish a causal saving or ROI. A supervised trial remains subject to site review and is not deployment approval.</p>"
    if agreement.brief.data_classification != "field":
        html += "<p>This simulated pilot demonstrates the workflow and does not establish field performance.</p>"
    return html
