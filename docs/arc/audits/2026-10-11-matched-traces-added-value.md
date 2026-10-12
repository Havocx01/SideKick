# Matched traces and AI added value

11 October 2026. Single local assessor, no subagents or engineer participant. Two new paid requests, no retries, current `gpt-4.1-mini-2025-04-14`, prompt `sidekick-deep-v18`. No training, reserved scoring, workspace consent changes or saved-user-record edits.

## Result

Matched, bounded score/warning excerpts now let a deep investigation inspect an actual selected history instead of relying only on aggregate rates. The UI separates **Recorded facts**, **Leading hypothesis · Possible explanation**, and evidence prerequisites. Scores cross thresholds; warnings activate or switch off. Unknown or incompatible histories stay unavailable. This improves the evidence and presentation, but does not establish that the AI makes engineers faster or more accurate.

Both new answers retained a tentative mechanism, an alternative and a diagnostic question. They add a score-response-versus-persistence distinction to the regular missingness/imputation/timing check. The distinction is potentially useful, but remains generic and can also be supplied deterministically. Only the comparison explanation cited a supplied matched-history record; both checks cited additional patterns whose matching histories were unavailable. Those missing patterns and historical fitted preprocessing remain explicit prerequisites. Neither answer established a cause, a remedy or a better model verdict.

## Recorded traces

Pairs must share candidate/configuration, development partition, equipment, threshold, failure cycle and exact cycle/RUL axes. Ambiguous versions are rejected. Up to two examples per model are selected, prioritizing missed/late outcomes. At most eight aligned score/active-warning samples per pair leave the server. No raw sensor readings, real equipment IDs or absolute equipment-cycle IDs are supplied; relative cycles before failure and pseudonymous histories preserve interpretation.

Each excerpt identifies omitted points and incomplete source windows. Samples keep their actual RUL; no interpolation occurs. High-score streaks follow the recorded scorer's convention: valid readings in sequence; invalid scores retain pending streaks/state; cycle gaps do not reset the scorer. Earlier-window context is included. Adjacent-cycle descriptive streaks are labelled separately. A crossing alone need not satisfy the opening rule. Compact excerpts cannot justify a threshold sweep.

The shipped benchmark and its existing SHA-bound reconstruction supplement were read without modification. For lr2, selected missed examples include a history with no useful-window crossings and another with a single crossing against a two-valid-reading activation rule. This is evidence about those selected histories, not all missed warnings or physical equipment behavior. Historical preprocessing cannot be inferred from today's source code.

## Paired answer review

The evaluator prepares four regular-analysis contexts: failing lr2, passing aug3, aug3/lr2 comparison, and an explicit missing-record fixture. It also reviews five immutable historical captures covering passing, failing, comparison, reversed order and missing supporting records. Two fresh captures are added. Historical prompts and legacy schemas are labelled; reviewing their content is not current production admission or fresh v18 generation. Repeated comparison captures are not independent samples.

| Fresh case | Regular next check | AI addition | Content judgment |
|---|---|---|---|
| Failing lr2 | Check missing-reading flags and median imputation; inspect late and missed warnings for the decisive dropout case. | Ask whether scores cross the model's own threshold while the warning remains inactive, with a weak-score alternative. | Potential diagnostic structure, not a demonstrated better action. It does not cite the supplied pair and extends the question to unrecorded patterns. |
| Aug3/lr2 comparison | Same concrete check, correctly prioritizing the failing lr2 candidate. | Contrast weak scores with delayed activation; the explanation cites a matched lr2 history. | Some evidence relevance, but no specific trace-derived mechanism. The causal wording in its short title is stronger than the explicitly tentative body. Engineer review/edits remain necessary. |

The regular verdicts, essential facts and source scope are retained. Server-owned procedures, controls, prerequisite checks and conditional branches must not be credited as new AI reasoning. Changed text is reported as a difference, not automatically scored as a win. The previous v17 answer's “warnings below/cross the threshold” language is now rejected when used as new output; its diagnostic question can remain. Historical saved records remain readable under their original currency without paid regeneration.

## Cost and latency

| Case | Input/output tokens | Estimated cost | Generation/processing seconds |
|---|---|---|---|
| Failing | 8,557 / 214 | $0.0037652 | 6.41 |
| Comparison | 8,633 / 200 | $0.0037732 | 3.07 |

Total **$0.0075384**, conservatively ignoring cached-input discounts, at the verified [published model prices](https://developers.openai.com/api/docs/models/gpt-4.1-mini). Exactly two provider dispatches; no third request or automatic retry. The durable ledger reserves cost before dispatch, counts failed requests, blocks duplicate cases and uses an exclusive live-run lock. The ceiling was two requests/$0.10; admission was initially stopped by a local harness error before any network request, then corrected.

These are machine generation times, not engineer decision times. No human decision times, quality scores or benefit percentage were invented.

## Reproduction and engineer measurement

Offline default, zero network clients:

```powershell
.venv/Scripts/python.exe scripts/evaluate_deep.py --output output/deep-review-new
```

This generates `results.json`, `review/review.html`, a blank `review/score-sheet.csv`, and a facilitator-only method key. Both answers receive the same original recorded evidence; A/B order alternates. Keep the key from reviewers. Assign independent reviewers or adjudicated equivalent cases to avoid learning effects. Score decisive facts, scope errors, feasibility/quality of the next check, edits and decision quality before speed. Record review time and generation wait separately. Blanks remain unobserved, never zero.

The new captures are immutable fixtures `deep_traces_failing_20261011.json` and `deep_traces_comparison_20261011.json`. Five older exact packets/answers/context snapshots are archived in `deep_evaluation_history_20261011.json`. Offline replay does not grant an older answer access to newly collected supporting records. Legacy contract reviews are marked separately from current-contract verification.

The two authorized live cases ran with:

```powershell
.venv/Scripts/python.exe scripts/evaluate_deep.py --live --case failing --case comparison --output output/matched-traces-20261011/live
```

The saved ledger is exhausted; do not delete it to repeat a paid suite. New paid evaluation needs a separately agreed budget. Review artifacts and the ledger are ignored local outputs, not user workspace mutations.

## Verification and remaining limits

Focused tests cover exact alignment, threshold/partition/failure mismatch, ambiguous versions, invalid scores, gaps, prior-window streaks, bounded inputs, raw-reading exclusion, source preservation, consent/reuse/brief behavior, precise warning/score wording, UI separation and evaluator budget/no-invented-benefit behavior. Fresh closeout: 408 backend tests passed (one Windows skip, three training integrations excluded), 44 relevant browser tests passed in both themes at mobile/desktop widths, seven protocol tests passed; Ruff, frontend lint, generated types, TypeScript and production build passed. Ambiguous browser selectors were repaired and the complete relevant suite rerun green. Evidence fingerprints are unchanged. Details are recorded in the implementation plan and ignored verification receipt; changes remain uncommitted and undeployed.

This task proves the implemented evidence/wording safeguards and reports actual content differences across selected saved cases. **Consistently useful explanations, improved engineer decisions and real-equipment reliability remain unproved.** The A/B pack makes those measurements possible; it does not claim they happened. This follows [task-specific and comparison-based evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices), with human judgment required for actual engineering value.
