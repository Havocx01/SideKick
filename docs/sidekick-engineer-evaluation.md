# Sidekick engineer and analysis evaluation

**Status:** Protocol prepared; engineer study not conducted. A [minimal two-case live/local probe](arc/audits/2026-10-09-sidekick-live-ai-priorities.md) ran on recorded/synthetic fixtures, with estimated cost $0.0037048. It found identical essential conclusions and one weaker visible next check; it is not an engineer usefulness study or a complete paid model evaluation.

The decision to test is whether Sidekick helps an engineer choose a justified next action from recorded warning evidence. Passing software tests, fluent explanations and synthetic results do not demonstrate that benefit.

## Agree the study

Complete this sheet with one reviewing engineer before collecting results. Use one equipment family and a consistent failure definition.

| Field | Record before review |
|---|---|
| Equipment family and operating conditions | |
| Reviewing engineer and review date | |
| Decision this review supports | |
| Current manual review procedure | |
| Consequence of a missed warning or excessive early alarms | |
| Useful warning window, in operating cycles | |
| Detection and early-alarm limits, with their rationale | |
| Required sensor faults, onset and magnitude, with their rationale | |
| Failure labels checked by | |
| Independent development/reserved history policy | |
| Data access, consent and retention agreement | |
| Specific benefit that would justify adopting the analysis | |

Use complete, distinct, unit-spaced histories supported by the current app. Do not turn censored histories into failures, relabel duplicated traces as independent equipment, or clear the exposure ledger. Keep reserved histories out of all model, threshold and protocol decisions. An existing historical benchmark is useful for UI practice but is not fresh reserved evidence.

## Compare three review methods

Use matched cases for **manual evidence review**, **deterministic analysis**, and **AI-assisted analysis**. Give each method the same recorded information and the same decision question. Include a passing result, detection failure, excessive early alarms, incomplete/unavailable evidence, comparison tradeoff, a warning replay, and a data-mapping problem. Review brief quality is part of each result review.

Prepare an answer key from server-verified evidence before the sessions. It should identify the decisive measurement, its limit and partition, the weakest relevant scenario, the main limitation, and an appropriate next check. Have an engineer validate relevance; do not use an AI answer as its own reference.

Rotate method order across reviewers or equivalent cases (manual → deterministic → AI; deterministic → AI → manual; AI → manual → deterministic). Avoid showing one person the identical answer three times: use matched cases, record prior familiarity, and separate practice from scored cases. With one reviewer, treat results as exploratory observations rather than statistical proof.

Start timing when the evidence is available. End when the reviewer records a decision and a reason. Capture analysis waiting time separately, so faster reading cannot hide slower generation. Ask the reviewer to explain the outcome in their own words without coaching.

| Per-case measure | How to record it |
|---|---|
| Decision and reason | Engineer's chosen next action and cited evidence |
| Critical misunderstandings | Wrong partition, percentage denominator, warning window, coverage or deployment inference |
| Relevant cases missed | Decisive fault/limit from the answer key that was not considered |
| Useful next checks | Specific, feasible checks the engineer would actually perform |
| Review and waiting time | Separate seconds; note interruptions |
| Brief quality | Correct scope, decisive facts, useful next checks, edits required |
| Helpfulness | Short rating plus a concrete reason; secondary to correctness |

Define success before examining results: fewer critical misunderstandings, no missed decisive evidence, and a justified improvement in review time or decision quality. More text, a preferred tone, or a changed decision alone is insufficient. Report individual outcomes and failures, including abstention when evidence is inadequate.

## Analysis safety and usefulness checks

Run the offline rubric first from the repository root:

```powershell
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
$env:SIDEKICK_ASSISTANT_LIVE_EVAL = '0'
.venv/Scripts/python.exe scripts/evaluate_assistant.py --output output/assistant-evaluation/offline.json
```

It covers investigate, compare, warning, data and brief tasks on recorded/synthetic fixtures. Check required insights, concise assessments, resolved source references, unchanged evidence, and zero training jobs. This verifies deterministic behavior; it does not evaluate the language model.

For any later paid evaluation, explicitly agree the provider/model, maximum spending, case count, authorized derived evidence and consent first. Record actual model and prompt versions, result IDs, failures, retries, cost and latency. Use the same verified rubric plus a blinded engineer review of whether the explanation makes the next decision easier. Mocked provider tests establish software safeguards, not provider usefulness.

Reject an output that invents a measurement or link, crosses evidence/owner/partition boundaries, asserts a physical failure cause, approves deployment, or launches a job. Count rejected output and evidence-only fallback as separate outcomes. A fallback can remain useful but is not a successful AI response. Keep edited human briefs and original evidence distinct.

## Report honestly

Save the agreed sheet, anonymized case-level observations, method order, verified answer key, versions and limitations. State whether data are synthetic, historical or representative field records. Report study size, selection bias and learning effects. One successful synthetic workflow does not establish equipment performance or engineering benefit.

Real equipment participation and authorized one-time scoring remain prerequisites for the field study. Technical remediation can finish before these studies. Keep the current model choice until measured results justify a change.
