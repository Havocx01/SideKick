# Experiment context and AI reasoning refinement

Status: DONE. Planned/effective assurance: Guarded. Saved input, paid admission, evidence scope and historical reuse require privacy and compatibility checks. Single local owner; no subagents, training, reserved scoring, deployment or commits. Preserve all existing authorized changes.

## Implementation state

Baseline HEAD: 3b0d54c951634e09bbe64731635d1f4bc3e6742b. Initial dirty hashes: ignored `output/context-ai-refinement-20261011/baseline.json`. Prior changes belong to this ongoing authorized session and remain intact. Arc runtime reference bundle is absent; follow scoped installed instructions and local review. Metadata excludes this plan and index.

Seams: separate experiment context metadata; optional pretraining Pilot brief inputs; local-only editing/read and explicit deep focus; bounded provider contract and paid/offline evaluation. At most two new paid requests, no retries, $0.10 conservative evaluation ceiling, same configured model.

<task id="context" kind="behavior" status="done">
<intent>Move shared context into the optional Pilot brief before training, persist separately from recorded evidence and allow later editing. Keep only an optional focused question in deep setup, and show exactly what context AI uses.</intent>
<verify>Backend context API/store tests; frontend context/deep browser cases; generated types.</verify>
<done>Context survives restart, cannot alter model/scoring evidence, no contact text copied, no paid request on editing, failures preserve drafts and local-only access/origin guards apply.</done>
</task>
<task id="reasoning" kind="behavior" status="done" depends_on="context">
<intent>Improve the model's evidence-bound reasoning contract without relaxing scope, numeric or causal safeguards. Permit abstention rather than forced explanation; distinguish useful reasoning from acceptance.</intent>
<verify>Semantic fixtures and at most two isolated paid requests, including exact-answer replay through reuse/brief/export.</verify>
<done>Report actual retained content and incremental usefulness; no fabricated pass or benefit percentage.</done>
</task>
<task id="closeout" kind="verification" status="done" depends_on="reasoning">
<intent>Review the attributable implementation and run the relevant fresh gate.</intent>
<verify>Ruff, backend, frontend lint/types, protocol, production build and affected browser tests.</verify>
<done>Green affected checks, documented limitations, changes uncommitted.</done>
</task>

## Decision log

Keep shared descriptions in a separate SQLite table instead of rewriting recorded pilot briefs/evidence. Only three explicit shared fields are seeded; reviewer/contact details remain excluded. Full-local editing includes the recorded benchmark, with its own metadata scope. A pre-run panel contains one optional focus and collapsed shared context; only Start admits work.

Preserve the existing Pilot brief capacities instead of shortening legacy equipment/decision fields to fit the previous request-scoped context. Shared/request snapshots now use the same 200/500/2,000 limits; focus stays 500. Evidence packet byte limits remain unchanged.

The first of two paid requests exposed an unqualified-score assertion after a tentative opening. Add exact negative coverage and check each explanation paragraph, while retaining single generic mechanisms under explicit hypothesis framing. The final response retained a conditional mechanism/alternative/check; both answers are immutable fixtures. No additional paid request is admitted. Review content usefulness separately from successful parsing and reuse.

## Completion receipt

Fresh final gate: **391 backend tests passed**, one Windows native-symlink skip, three integration jobs deliberately deselected. Ruff, frontend lint, TypeScript through the production build, exact generated-type consistency and **7 protocol tests** passed. The production build retains the existing chunk-size advisory. **40 browser checks** passed across deep/context/presentation/recovery suites. Pretraining tests intercept the experiment POST before any job; no training or reserved scoring is launched. The mechanical design detector returned no findings. Mobile light Pilot brief and mobile/desktop dark setup screenshots were inspected; automated cases cover both themes at 390/1280 px.

Two paid requests, estimated **$0.0065304**, same current model, no retries or third request. The final answer retained one tentative explanation, one competing alternative and one diagnostic. Exact captured-answer replay checks reuse, restart, conversion, save and export with zero further paid requests. The earlier unsafe answer retains no explanation under the final guard. [Content evaluation and remaining limits](../audits/2026-10-11-context-ai-refinement-evaluation.md).

Whole-change local review covered separate metadata and request snapshots, no automatic contact copying, local/origin guards, empty-focus historical identity, context edit failures, admission separation, alias/model scope, abstention versus rejection, fixed diagnostics, brief/export parity, focus return and natural mobile scrolling. The final conditional framing is useful to investigate but closely follows the example, uses warning/score terminology loosely and requires missing records. It does not establish consistent reasoning quality or an engineer benefit percentage; safeguards are not a proof for every unfamiliar output.

Implementation hashes and command receipts: ignored `output/context-ai-refinement-20261011/verification.json`. Evidence bundle SHA-256 remains `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`. The user workspace and server were not modified/stopped by checks. Changes are uncommitted and undeployed.
