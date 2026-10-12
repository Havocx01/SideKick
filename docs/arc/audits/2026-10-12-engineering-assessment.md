# Sidekick: AI-assisted engineering assessment

12 October 2026. Reviewed source revision: `556fc2b72d2d0cf89183adfc08d29b15ab62990c`. One AI assessor; no human engineer participated. This is an evidence-based technical review, not professional certification, field validation or a measured usability study. Zero new provider requests. Original saved packets and responses were reviewed; newer evidence was not attributed to older answers.

## Decision

Sidekick is suitable for a supervised evidence-review rehearsal. Its recorded results justify investigating lr2's sensor-dropout weakness and considering aug3 for a separately agreed fresh validation study. They do not justify equipment deployment, changing maintenance policy, claiming that augmentation caused the improvement, or changing an alert rule solely to improve these benchmark results.

Routine analysis gives a useful first action. Deep AI adds a diagnostic branch, but the latest two answers do not resolve that branch using the supplied histories. Use it as a question generator requiring evidence review; its incremental value over a deterministic diagnostic checklist remains unproved.

## Case-level assessment

| Case | Evidence and decision | Regular analysis | Increment from retained deep AI | Review judgment |
|---|---|---|---|---|
| Failing lr2 | 57/64 required fault cases pass; decisive persistent dropout on sensor_8 warns 41/80 histories in time, below the recorded 70% minimum. | Points to missing-reading flags, median imputation and late/missed warnings. | Asks whether weak scores or alert persistence explains misses; cites aggregate patterns rather than the supplied matched record. | A relevant diagnostic branch, but not an explanation established by evidence. Start with the stored failed case and its matched traces. |
| Passing aug3 | 64/64 required cases pass; the weakest recorded case still warrants scrutiny. | Directs attention to recorded drift sensitivity and channel scaling. | Only older saved AI output exists for this case in the pack; no new v18 paid generation was performed. | Passing demonstration limits supports further evaluation, not deployment or calibrated fleet reliability. Do not count historical AI retention as a new success. |
| aug3 versus lr2 | aug3 meets all recorded limits; lr2 does not. Worst fault types differ, and the configurations were independently selected. | Correctly prioritizes the failing dropout case and preserves the comparison limitation. | One retained explanation cites a matched lr2 record; its short title, “Weak score response causing missed warnings,” is stronger than the tentative body. | The comparison decision is already available locally. Treat the AI title as a hypothesis; do not infer statistical superiority or the causal benefit of augmented training. |
| Missing matched evidence | The aggregate result still identifies the failed model; fitted preprocessing or matching histories may be absent. | Gives a first inspection step but cannot establish the mechanism. | The report's prerequisites require the missing records; fallbacks preserve local evidence. | Obtain records or abstain. Neither current source code nor an AI explanation substitutes for the historical fitted pipeline. |

These are selected historical/fixture cases, not independent random samples or a representative operating fleet. The twelve-case manual/local packet covers additional alarm, replay and mapping issues; no new AI answers were invented for those cases.

## What the matched histories actually establish

The failing capture's `history-summary-1` and `history-summary-2` are the same persistent-dropout pattern, matched to clean histories with the same model, cycle axis and threshold (approximately 0.996798). The useful window is 30 through 10 cycles before failure. The recorded opening rule requires two consecutive valid scores at or above threshold.

* First selected history: clean has nine useful-window scores at/above threshold and eight active-warning cycles; faulted has one crossing, longest high streak one and zero active-warning cycles. The isolated crossing is insufficient for the two-reading opening rule. No persistence implementation defect is established.
* Second selected history: clean has eleven crossings and ten active-warning cycles; faulted has no useful-window crossings and no active-warning cycles. Altering persistence alone cannot activate a warning without the required score evidence under the fixed threshold/rules.

For these two examples, reduced sustained score response is directly observable. Its preprocessing/feature mechanism and physical equipment cause are not established. Do not extend this explanation to every missed history, other dropout/stuck patterns, or unseen field equipment. The brief eight-point excerpt omits most recorded points, including some transitions: inspect the full stored replay before judging exact activation timing. Whole-window counts and streak summaries are not the same as adjacency between sampled points.

The comparison capture includes an aug3 example with delayed activation but a timely outcome, and an lr2 missed example. These examples are not a controlled same-fault population comparison. Scores from different models have different thresholds; their numerical magnitudes alone are not a calibrated ranking of confidence.

## Justified next check

1. Open the decisive lr2 dropout case and inspect the full clean/faulted stored development traces together. Keep the model, own threshold, useful window and opening/closing rules fixed.
2. Confirm whether each history loses sustained score crossings or has sustained crossings without the recorded activation. Review prior-window streak context and invalid-score handling; do not treat gaps in the sampled excerpt as consecutive readings.
3. Obtain the fitted historical preprocessing record before attributing the score loss to missing-reading flags, imputation or scaling. If unavailable, record that limitation. Current implementation details cannot prove how this older model was fitted.
4. If a future development-only controlled replication is agreed, vary one input-handling factor at a time and record the new model/configuration identity and resulting timings. Do not reuse exposed reserved histories or silently recalibrate the existing evidence.

This procedure sharpens the generic AI question using supplied facts; it is the assessor's synthesis, not an improvement already demonstrated by the paid answers or a new training result.

## Priorities from the review

* **Before claims of usefulness:** a real reviewer must score justified actions and scope errors, then record review time separately from generation latency. No numerical AI benefit is established by this assessment.
* **Before a field pilot:** obtain a suitable equipment family, real documented failures, meaningful units, failure labels and a reviewing owner. Agree window/fault magnitudes and acceptance criteria before training. Healthy-only or censored logs require a different protocol rather than relabelling the last reading as failure.
* **Next AI refinement candidate:** require explanations to distinguish available matched-history observations from unrecorded patterns; make causal titles explicitly tentative. Keep a deterministic score/persistence checklist as the comparator. This review identifies the need; it does not claim a prompt change was implemented or live-tested.
* **Next trace presentation candidate:** ensure readers can find the decisive score transition in the full replay, since a bounded sample may omit it. Do not increase provider input indiscriminately.

## Reproduction and materials

Generated offline with existing tools:

```powershell
.venv/Scripts/python.exe scripts/prepare_engineer_evaluation.py --output output/release-review-20261012/engineer-pack
.venv/Scripts/python.exe scripts/evaluate_deep.py --output output/release-review-20261012/deep-pack
```

The manual/local packet has twelve cases; the deep pack has four regular contexts, five historical captures and two recent captures. These are not eleven independent AI trials. Use original source JSON and facilitator keys to verify observations. Human sheets remain blank. [Pilot and user-session guide](../../sidekick-review-sessions.md) describes the external sessions still needed.
