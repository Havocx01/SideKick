# Deep AI usefulness: paired captured-response review

11 October 2026. Single Codex assessor; no subagents or engineer participant. **Zero new paid requests**, no training, reserved scoring, user-record edits or application behavior changes.

## Conclusion

The regular analysis is the stronger source for decisions about recorded limits, measured warning loss and validation boundaries. Deep AI offers some additional investigation structure, particularly distinguishing score weakness from alert persistence. It has not demonstrated consistently better next checks, improved engineer decisions or saved review time. Keep it as an optional source of proposed explanations; do not describe it as a more accurate analysis or rely on its verification status as a usefulness certificate.

This review compares actual saved provider answers, not hand-authored model mocks. It finds quality defects in some reports that the current verifier accepts. A repaired contract and passing software tests do not establish useful reasoning.

## Method and sample

Before reviewing content, the criteria were: factual/scope correctness, feasible checks, controlled comparisons, informative competing outcomes, and incremental value over regular analysis. Reordered facts or more text do not count as added value. This follows the distinction between task-specific evaluation and generic fluency in [OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

The six saved outputs cover three distinct model combinations: passing aug3, failing lr2 and aug3/lr2 comparison. Four outputs repeat the same comparison, including reversed candidate order and two later enriched prompts. They are selected debugging captures, not independent or representative samples. Original prompts are v7, v8, v9 and v10. They were replayed through the current v11 processing without a network client. This is **not fresh v11 generation** or an estimate of its future success rate.

For each capture, the probe checked exact equality of the originally supplied fault-pattern observations against the current recorded bundle and preserved candidate order. It retained the original packet and answer so that later supporting inputs cannot be credited to an earlier model response. Regular analysis used the same models, partition and bundle. The original optional context remains visible in the enriched cases.

Automated checks covered source scope, unchanged server findings/summary, resolved citations and links, and unchanged evidence. A separate content review examined the actual retained explanations, alternatives, procedures and conditional outcomes against the original packet and the local next checks. This is an informed software/domain review by one assessor, not a blinded engineer study or an independent causal validation.

## Results

All 12 existing regular-analysis evaluation cases passed, including results, comparisons, replay, data readiness/mapping and briefs. Those are deterministic regression cases, not 12 paid AI comparisons. All six captured-response probes passed the structural checks. Current processing retained **three full reports, two partial reports and one fallback**. These counts describe retention only; they are not a usefulness score or a provider success rate.

| Saved output | Current retention | Added value versus regular analysis | Main limitation |
|---|---|---|---|
| Passing aug3, v7 | Full | Limited: adds threshold/dropout alternatives and conditional outcomes. | Suggests sweeping thresholds to improve detection without requiring an early-alarm burden check. It also talks about late warnings when the aggregate packet does not establish which undetected histories were late. The local answer already identifies the weakest case, one lost warning and the validation boundary. |
| Failing lr2, v7 | Full | Limited: relates failures to dropout/stuck input handling. | The local answer already provides missing-reading flags, median imputation and late/missed-warning checks. Proposing adaptive thresholds adds complexity and omits the alarm-burden tradeoff; proposing imputation without fitted preprocessing records is not a demonstrated remedy. |
| Original aug3/lr2 comparison, v8 | Partial | Limited: the retained threshold check mentions both detection and excessive early alarms. | The generated feature-augmentation explanation and procedure were removed. A retained gap speculates about incomplete training from absent coverage metadata; that absence cannot establish training incompleteness. |
| Reversed lr2/aug3 comparison, v8 | Full | Poor: extra detail can direct an engineer toward an invalid comparison or impractical inspection. | It proposes synchronized numeric thresholds across different score scales. Another test is titled “Feature Representation Analysis via Intermediate Layer Inspection”; the compared warning models are logistic regression and trees, not neural networks with intermediate layers. Relevant citations did not make those checks valid. |
| Enriched comparison, v9 | Fallback | No AI-specific value after rejection; the regular evidence remains available. | The original answer invented augmented input features and affirmed a hypothetical outcome. Safe fallback is not successful AI reasoning. |
| Enriched comparison, v10 | Partial | Potentially useful: checks whether scores cross the model's threshold but fail to sustain an active warning, with different implications if they never cross it. | This is more specific than the regular comparison's first navigation action. However, the matched clean/faulted summaries were supplied only for aug3, not lr2. Relevant lr2 traces and historical preprocessing need to be available before carrying out the suggested check. No engineer has validated its practical value. |

None of the outputs establishes a better model-qualification decision than regular analysis. The verdicts and measured findings remain server-owned. The clearest potential addition is a structured next-check question, not a newly proven mechanism or physical failure diagnosis. Some of that improvement could also be provided by deterministic diagnostics, without an LLM.

The latest retained answer's useful distinction is:

1. Inspect the affected model's development scores relative to its own threshold, plus consecutive crossings and active-warning transitions.
2. If crossings occur without the required sustained warning, investigate alert persistence and timing.
3. If scores remain low, examine recorded preprocessing, missingness and feature response as competing possibilities.

These are proposed diagnostic branches. Neither branch confirms a cause, and unrecorded traces must not be invented. The current answer still uses overconfident wording inside the server's tentative wrapper, such as “primarily due to”; this weakens its uncertainty communication.

## Findings that deserve priority

**U1 — P1: Verify experimental meaning, not just citation membership.** Current processing accepts the reversed comparison's synchronized thresholds and intermediate-layer proposal. Add offline semantic acceptance cases for differing score scales and the supported model families. Proposed threshold changes must include detection and early-alarm burden, fixed-model scope and development-only checks. A generic missingness prefix does not repair an invalid procedure.

**U2 — P1: Require observable evidence and conditional language.** An aggregate undetected count does not distinguish late from missed warnings or identify their histories. Coverage metadata gaps do not establish incomplete training. Match a proposed check to available traces/preprocessing, or clearly identify required evidence as a prerequisite. Do not frame an unobserved mechanism as “primarily” responsible merely because the UI adds “Possible explanation”.

**U3 — P2: Measure benefit separately from retention.** The regular comparison's first action often points at the first model's replay even when the other candidate fails. AI can improve that focus, but deterministic action ranking could as well. Test the two approaches against the same evidence. Count partial reports, fallback, required edits, invalid checks and generation time. Avoid reporting five retained outputs as five successful useful answers.

No product fixes were applied during this evaluation. These findings qualify the preceding technical closeout: the safeguards/lifecycle passed their tests, while semantic usefulness still has unresolved gaps.

## Reproduce and inspect

The ignored `output/deep-usefulness-20261011/probe.py` contains the six-capture manifest, replaces the provider with a parser of exact saved output, and admits no network request. It asserts exact original pattern scope before replay. Run from the repository root:

```powershell
.venv/Scripts/python.exe output/deep-usefulness-20261011/probe.py
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
$env:SIDEKICK_ASSISTANT_LIVE_EVAL = '0'
.venv/Scripts/python.exe scripts/evaluate_assistant.py --output output/deep-usefulness-20261011/local-rubric.json
```

Artifacts: `paired-results.json` contains original packets/answers, local answers, retained reports and checks; `local-rubric.json` contains the 12 local cases. They live in the same ignored folder. Paid captures came from the earlier live-repair, comparison-repair and final-check ledgers; this task did not add a paid request to any of them. No credentials or raw sensor readings were copied into the review artifacts.

The evidence bundle SHA-256 remains `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`.

## What remains unproved

Follow-up: the [diagnostic-contract implementation and four-request evaluation](2026-10-11-deep-check-contract-evaluation.md) addresses the known unsafe procedures and inverted branches. It retains a scoped question when explanations fail, with explicit evidence prerequisites. That follow-up still does not demonstrate consistently useful generated explanations or improved engineer decisions; this original review remains the pre-change record.

The AI has not been shown to reduce review time, prevent misunderstandings or improve engineer decisions. The next meaningful validation is an engineer comparison of regular versus AI-assisted analysis on matched, representative cases, using the existing study protocol and scoring invalid checks as failures. Any future paid fresh-generation evaluation needs a new explicit request/spend ceiling; no larger-model recommendation is justified by this sample.
