# Sidekick: first equipment pilot

Status: equipment family, field data and reviewing engineer are not yet confirmed.

The question is simple: does testing sensor failures help an engineer make a better decision about an equipment warning model?

## Find a suitable partner

Ask an ABB contact or maintenance engineer for one equipment family they know well. Choose it based on access to usable records and a reviewer, rather than guessing which asset makes the best demo.

Use these questions in a short discussion:

- Which equipment already has sensor histories and documented failures?
- How do you currently assess failure warnings?
- How far ahead must a warning arrive to allow action?
- Which sensor problems occur in practice?
- What decision could this test change?

Proceed when one engineer can review the labels, operating conditions and test limits. If only healthy operating logs are available, record that gap. The current app cannot evaluate those as complete failure histories.

## Check the data before training

The local app accepts a CSV up to 10 MB, with at least 25 complete equipment histories. It reserves 20 histories and uses five equipment-separated folds on the remainder. At the minimum size only five histories remain for development, so a successful upload is not evidence of a strong study. Agree a useful sample with the engineer and record its limitations.

| Required information | What to check |
| --- | --- |
| Equipment ID | One identifier per complete equipment history. Record repeated assets or rebuilds; do not assume they are independent. |
| Cycle index | Integer operating cycles, with one reading per equipment/cycle pair. Record the actual sampling interval. |
| Sensor columns | Numeric readings. Document units, sensor meaning, missing values and operating regimes. |
| Failure information | A consistent failure cycle for each history, including a reading at that cycle. Without that column, explicitly confirm that every history actually ends in failure. |
| Scope | One equipment family, known failure definition and relevant operating conditions. |

Timestamps and censored histories are unsupported. A censored history ends before a documented failure. Do not relabel its last reading as failure or turn hours into arbitrary cycles. If these are the only records available, agree a data adaptation before running the pilot.

Record omitted histories and why they were omitted. Results on failed assets alone do not establish behavior across a whole operating fleet.

## Agree one test

Before training, write down:

- The decision: for example, whether to investigate a candidate for a supervised trial.
- The useful warning window in operating cycles.
- Minimum warnings in time and maximum early-alarm time.
- Required sensor faults, their sizes and when they begin, justified by the engineer.
- The current review procedure and what counts as useful evidence.

The 70% detection and 10% early-alarm defaults are demonstration settings. Early-alarm time measures warning time during eligible early cycles; it is not the percentage of individual warnings that are false.

Train using development histories. Then open **Equipment pilot**, record the reviewer and agreement, and save it before reserved scoring. Pilot checks are declarations by the reviewer, not independent verification by Sidekick.

## Freeze, evaluate and review

1. Check the development result and its named failure reasons. If none qualifies, keep that outcome and revise the study using development data.
2. Freeze the qualifying recommendation. Keep reserved histories out of model, threshold and protocol decisions.
3. Confirm the reserved histories are untouched, then evaluate once. Once scoring starts, an interrupted attempt still exposes those histories. Do not clear the ledger to rerun them as fresh evidence.
4. Ask the engineer to inspect warnings in time, late and missed; highest early-alarm time; required fault coverage; and representative replay examples.
5. Record the next action and observations in **Equipment pilot**. A passing result can support discussion of a supervised trial. It does not approve deployment.

If a final result fails, record that failure. Any retuning needs another genuinely untouched evaluation set before an independent claim.

## Measure usefulness and keep the evidence

Ask what weakness the engineer learned about, whether it changed their decision, and what remains unclear. Record the current procedure's review time and Sidekick review time for comparable tasks, if available. The app stores these as self-reported observations. One review cannot establish savings or prove that Sidekick caused a change.

Export the pilot ZIP. Keep a short case study with:

- Equipment family, data source, failure definition and excluded records.
- Agreed settings, actual development/reserved counts and source identifiers.
- Healthy and faulted results, the deciding fault/limit and coverage gaps.
- Engineer observations, next action and any recorded review times.
- Limits and the next validation needed.

Until field records and a real reviewer are available, use a synthetic experiment to rehearse this process. Label it as simulated and leave field benefit unverified.
