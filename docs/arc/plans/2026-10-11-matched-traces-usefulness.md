# Matched traces and AI added value

Status: DONE. Planned/effective assurance: Guarded, because recorded traces inform paid qualitative reasoning. One local owner; no subagents, training, reserved jobs, commits or deployment. Preserve the ongoing session's existing changes. Installed Arc runtime reference files are unavailable; use scoped local verification and sequential review.

## Implementation state

Baseline HEAD: 3b0d54c951634e09bbe64731635d1f4bc3e6742b. Dirty fingerprints: ignored `output/matched-traces-20261011/baseline.json`. Prior dirty paths belong to this authorized ongoing work. Commit posture: leave uncommitted. Evidence bundle/supplement remain unchanged.

Seams: read-only paired replay extraction; provider wording and verification; visible facts/hypotheses/gaps; reproducible offline and bounded paid added-value evaluation. Declare paths: `backend/app/assistant/{warning_traces,deep_support,diagnostic_checks,deep}.py`, `frontend/src/components/DeepReportView.tsx`, affected tests, `scripts/evaluate_deep.py`, documentation and immutable captures. No database or recorded-evidence schema migration.

<task id="traces" kind="behavior" status="done">
<intent>Supply aligned bounded score/active-warning samples from compatible stored development histories, preserving scope, threshold and gaps. Never reconstruct missing records.</intent>
<verify>.venv/Scripts/python.exe -m pytest tests/test_warning_traces.py tests/test_deep_evidence_inputs.py -q</verify>
<done>Tests cover pairing, exact values, persistence semantics, gaps, nonfinite scores, budgets and privacy.</done>
</task>
<task id="wording" kind="behavior" status="done" depends_on="traces">
<intent>Separate recorded facts, tentative mechanisms and missing evidence; reject warning/score threshold confusion without rewriting unsafe answers.</intent>
<verify>Focused deep backend tests and frontend deep-investigation browser suite.</verify>
<done>Existing saved outputs remain readable and requests reuse without automatic regeneration.</done>
</task>
<task id="evaluation" kind="verification" status="done" depends_on="wording">
<intent>Compare regular and AI output on passing, failing, comparison and missing-evidence cases. Replay previous captures offline and allow at most two new paid requests, no retries, $0.10 ceiling.</intent>
<verify>Offline evaluation, bounded live capture, exact answer replay; Ruff, backend, lint, generated types, build and browser checks.</verify>
<done>Report real content differences separately from acceptance. Create a blinded engineer comparison pack; do not invent human decision times or benefit claims.</done>
</task>

## Decision log

Existing replay bundles already contain matched histories. Expose bounded snippets rather than starting scoring or training. Protocol alert streaks count valid readings in recorded order; invalid scores hold state, so adjacent-cycle streak summaries are not substitutes for persistence semantics. Samples are excerpts, never complete traces for threshold tuning. Paid checks use only the shipped benchmark in an isolated temporary service.


Two paid dispatches completed, estimated $0.0075384; immutable captures saved. Both retain one tentative mechanism/check, but guidance remains generic and unproved as an engineer benefit. No more paid calls. The first harness invocation stopped locally before admission due to a nonexistent cache-clear method; this was corrected without a provider request. Exact original packets remain attached to historical reviews, so new traces cannot be credited to older answers. Legacy schema reviews are explicitly not current production admission. A/B packets use shared evidence and blank human observations.

## Closeout receipt — 2026-10-11

Sequential review checked pairing, full prior-window streak semantics, source privacy, citation/brief compatibility, UI distinctions and evaluation attribution. No unresolved technical blocker found in this slice. Historical outputs remain accessible without automatic paid regeneration; qualitative title/body strength and generic advice remain explicitly recorded evaluation limitations.

Fresh gate: **408 backend tests passed**, one Windows symlink skip and three training integration jobs deliberately deselected; **44 relevant browser tests passed**, including both themes at 390/1280 px; **7 protocol tests passed**. Ruff, frontend lint, generated-type byte consistency, TypeScript/production build and diff whitespace checks passed. The first final browser attempt had six ambiguous-selector failures; scoped status/heading selectors repaired those without weakening behavior assertions, and the full 44-test suite passed afterward. Final desktop/mobile screenshots were inspected. Existing build chunk-size advisory remains.

Offline review covers four regular contexts plus five historical and two new captures; these are not eleven independent AI trials. Exactly two paid calls, no retries, $0.0075384 estimated total. Engineer quality scores and decision times remain unmeasured. [Evaluation and reproduction](../audits/2026-10-11-matched-traces-added-value.md) records the honest result and blinded review procedure.

Recorded bundle and replay supplement SHA-256 fingerprints match the baseline. No training, reserved validation, consent changes or user-data edits were made. Ignored receipt/logs: `output/matched-traces-20261011/verification.json` and adjacent gate logs. Changes remain **uncommitted and undeployed**; restart the local API to load the backend changes. This completes the implementation and machine evaluation, not the separate human-benefit milestone.
