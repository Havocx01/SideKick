# Sidekick: minimal live AI evaluation and consolidated priorities

Date: 2026-10-09  
Reviewed implementation: `046a97240e852c8818d5da6baaccd5a4e5a88cae` plus the current uncommitted remediation changes  
Method: three independent Codex council members, actual paired live/local fixtures run by the chair, and anonymized peer review by all three. The council itself used no external model API. Only the two authorized application analyses below used the paid provider.

## Result

Live AI completed successfully and retained the correct recorded conclusions on both selected cases. It added **no observed decision-relevant information** beyond the local analysis in this sample. In the failing-model case, it selected a less useful visible next check.

This warrants two additions to the existing list: protect specific next-check guidance, and require demonstrated incremental value before spending calls and waiting time on equivalent analysis paths. It does not establish that AI is useless for every workflow or that another model would solve the problem.

The full [current implementation review](2026-10-09-sidekick-current-review.md) remains the source for existing R1–R7. Its statements about no paid calls refer to that earlier review; this follow-up records the newly authorized minimal live probe.

## Exactly what ran

Used the app's configured **OpenAI `gpt-4.1-mini-2025-04-14`**, prompt `sidekick-investigation-v4`, existing `enhance_analysis → investigate → scoped evidence tools → finish` path. The model and production instructions were not changed. The wrapper only metered requests, enforced evaluation limits and saved paired outputs.

Selected two cases rather than the full 12-case live suite:

1. **Failing recorded model, Logistic regression lr3:** discretionary fault investigation is where this architecture has the most opportunity to select useful additional evidence.
2. **Synthetic data with missing sensor readings:** checks a different task and its actionable readiness/mapping information.

Each ran once, sequentially. The local counterpart used fresh tools with identical context and evidence. No extra live brief was needed: converting an existing result uses deterministic `with_brief`. Comparison/replay/passing cases were not paid-tested. After the two cases showed clear parity and a specific guidance issue, all three reviewers agreed that another paid case was unnecessary for the immediate decision.

Limits: at most two logical cases, 12 provider requests, conservative estimated $0.10 ceiling, zero automatic SDK retries, the app's 45-second per-analysis timeout. Actual usage was **8 Responses API requests**, **7,846 input tokens / 354 output tokens**, zero cached tokens, and estimated **$0.0037048** total. That is approximately 0.37 US cents, not an invoice. Rates were verified from [official GPT-4.1 mini pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini): $0.40 input and $1.60 output per million text tokens. There were no paid model graders or model-comparison sweeps.

Only the committed historical benchmark and generated synthetic data were used. The normal scoped/aliased tool payloads were sent; no private user CSV was used. Fixture workspaces stayed under ignored `output/live-ai-review/`. All recorded evidence-file hashes remained unchanged and the fixture experiment table contained zero training jobs. No training or reserved-validation jobs, server/app configuration changes, commits, pushes or deployments occurred.

## Paired measurements

| Case | Local result construction | Live provider/tool path | API requests | Estimated cost | Observed difference |
|---|---:|---:|---:|---:|---|
| Failing lr3 result | 4.4 ms | 9.50 s | 5 | $0.0024356 | Same three essential claims and same inspected fault; AI promoted a generic matrix link above specific dropout checks. |
| Missing readings | 0.33 ms | 3.58 s | 3 | $0.0012692 | Same three essential claims and identical mapping; findings reordered. No demonstrated added decision information. |

These are single-attempt harness timings. Local timing measures result construction after shared evidence/file preparation; live timing includes provider requests and tool work. They are not full UI latencies, statistics, throughput benchmarks or measured engineer review times.

Both local/live outputs passed the existing four checks: resolvable references, required claim-ID families, at most three assessment claims, and brief-length constraint. The tested outputs contained no observed unsupported measurement, physical-cause diagnosis or deployment approval. This is case-specific inspection, not a comprehensive safety certification. Both evaluated `brief_draft` fields were null because neither task was a brief; the brief-length check did not evaluate an actual brief.

The meaningful additional evaluation was paired comparison of essential facts, inspected cases, mapping and visible next-check quality. The app authors the displayed claims and enforces critical ones, so a passed claim-ID rubric alone does not show that the model improved the analysis. This distinction follows [OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices): define task-specific criteria, compare results and calibrate with human feedback.

### Concrete failing-model observation

Both outputs correctly retained these facts:

- 63 of 64 required fault cases passed, so the model did not meet the recorded limits.
- Persistent dropout on sensor_13 from 60 cycles out: 54/80 histories warned in time, 67.5% against a 70% minimum; two more timely histories would meet that threshold.
- The fault case lost 26 timely warnings relative to healthy readings; the result does not establish a physical failure cause.

The local first action was the specific fault check: examine missing-reading flags, median imputation, and late/missed warnings before retesting. Live selected the generic action: **Review the recorded fault matrix for Logistic regression (lr3).**

The specific action still exists second in the live result JSON. However, `frontend/src/components/AnalysisInspector.tsx:228–231` renders only `result.actions[0]`, and evidence disclosures do not render the remaining actions. The UI's visible Next check therefore loses the concrete guidance. `backend/app/assistant/evidence.py:270` likewise uses only the first action when preparing a brief. That brief consequence is source-verified, not an observed live brief/export failure.

### Concrete data observation

Both outputs gave identical readiness, missing-reading and mapping-caution claims, and identical suggested column roles. They described one channel with 10% missing readings and explained median imputation with flags. Failure-record confirmation remained required. AI changed finding order but did not provide a different supported check or mapping.

The data path forces the two tool calls, and essential claims come from the same verified catalog. The observed parity is unsurprising; it is not proof that the model lacks intelligence. It indicates that this particular application path spends provider calls largely on choices already resolved locally.

## One consolidated priority list

Order reflects privacy-contract enforcement, preserving user work, avoiding unnecessary jobs, then useful output and verification. P2 items are material fixes before technical closeout; the AI-value item is explicitly a product/measurement priority rather than a universal software defect. Existing findings are linked by their original review IDs.

| Order | Priority and issue | Required outcome / acceptance evidence |
|---|---|---|
| 1 | **P2 — Preserve cloud provenance through migration and revocation** (R3) | A migrated cloud-derived brief cannot survive revoked consent or carry into a new evidence-only analysis. Add a combined migration → revocation → reuse fixture; preserve provenance independently of result schema. |
| 2 | **P2 — Revalidate completed analysis when reopened** (R4) | Refresh ownership/access/consent/expiry without automatically starting paid work. Explicitly check or identify model/prompt currency; GET alone currently serves historical output. Cover revoked and expired completed records. |
| 3 | **P2 — Protect current brief edits from delayed save acknowledgements** (R2) | Older Save responses cannot revert newer text. Saved/export state refers to the acknowledged current revision. Cover typing during Save, queued autosave and close/reopen. |
| 4 | **P2 — Preserve pending analysis identity through close/reopen** (R1) | Hiding before the initial response returns retains the admitted job; one start, no incidental cancel, no replacement request. Explicit Cancel remains available. |
| 5 | **P2 — Preserve specific, evidence-backed next checks** (new, live-supported) | A generic navigation action cannot outrank relevant inspected-fault guidance. Verify the visible Next check and deterministic brief conversion retain the dropout/imputation/late/missed checks. Do not add every action to the UI as clutter. |
| 6 | **P2 product priority — Make paid analysis demonstrate added usefulness** (new, bounded evidence) | Keep the single analysis workflow and evidence safeguards. Avoid repeated paid work on demonstrated equivalent paths, or define a supported extra task that improves the next decision. Extend the rubric beyond claim-ID compliance to action quality, essential-fact retention and incremental value. Keep the current model until evidence warrants changing it. Two runs do not justify claiming every path is redundant. |
| 7 | **P2 — Finish browser closeout and meaningful regression coverage** (R5) | Correct the five fixture-suite failures and stale POST-on-reopen expectation; distinguish harness failures from app defects. Add coverage for items 1–5 and preserve admitted-job recovery. Complete the outstanding isolated synthetic integration gate and document results. Docker runtime verification remains dependent on the stopped engine. |
| 8 | **P2, conditional — Bound public replay persistence** (R6) | If replay is externally published, bound retention, avoid persistent analysis or keep the target private. Current Render/default Docker uses demo, whose caps are implemented; do not mislabel this as a current demo failure. |
| 9 | **P3 — Run focused protocol tests in CI** (R7) | Add the separate seven-test protocol command to the standard workflow; Playwright `npm test` does not run it. |

No earlier resolved baseline finding is relabelled as open here. No application fix has been implemented in this evaluation step.

## Limits and next verification

This sample does not measure engineer decisions, real-equipment reliability, comparison or replay performance, live brief generation/export, unusual evidence, repeated-run stability or another model. There was no reviewing engineer. The [engineer evaluation protocol](../../sidekick-engineer-evaluation.md) still needs its counterbalanced manual/local/live study before an engineering-benefit claim.

Use the saved failing-result output as a regression fixture for action ranking; repairing it should not require another paid call. Reuse offline fixtures for lifecycle/consent changes. Run another tiny live probe only if a material provider/prompt behavior changes or an unresolved question genuinely requires it; do not rerun this pair simply to show progress.

## Reproducibility and council disposition

Ignored local artifacts:

- `output/live-ai-review/evaluate_minimal.py`: review-only metered wrapper around the actual app provider path. Running it sends paid requests; do not run it as routine CI.
- `paired-results.json`: complete paired answers, context, current prompt/instruction, per-request usage and unchanged-evidence/no-job results.
- `comparison-summary.json`: ordered claims/findings/actions, mappings and equality comparisons. Equal null brief fields are not brief coverage.
- `meter.json`: request/model IDs, input/output usage, timings and cost estimates. Credentials were not written or printed.

All three council members independently supported the observed next-check downgrade and lack of added insight in this sample. Peer review emphasized preserving specific guidance separately from the broader value question, accurately limiting timing claims, and keeping conditional replay exposure distinct from current demo behavior. Rankings differed; the synthesis rests on artifacts and source verification rather than votes. All agreed no additional paid case was needed now.
