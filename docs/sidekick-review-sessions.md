# Sidekick pilot and first-time-user review

Prepared 12 October 2026. No human sessions or real-equipment pilot have been conducted. The separate [AI-assisted engineering assessment](arc/audits/2026-10-12-engineering-assessment.md) reviews recorded evidence; it must not be presented as observed engineer behavior.

## Start a small review

Use the generated packets under `output/release-review-20261012/`. `engineer-pack/reviewer/manual.html` and `local.html` cover twelve evidence/data cases. `deep-pack/review/review.html` compares regular and saved AI answers. Keep facilitator keys and answer sheets separate from reviewer materials. The pack is a benchmark rehearsal, not field data. Original score sheets remain blank until a participant supplies observations.

Ask one reviewer to complete two or three cases first. Record prior familiarity and use an adjudicated answer key. Independent reviewers or equivalent cases are preferable to showing the same person the identical answer twice. A small exploratory review can expose misunderstandings; it cannot establish statistical superiority.

Agree the question before review: **What next action is justified, and what evidence would you still need?** Score scope correctness and action quality before timing. A useful outcome is a feasible check with the right model, fault, partition and missing prerequisites. Fluent prose and a preferred visual style alone do not qualify.

Do not show the AI-assisted assessment as a correct-answer prompt to participants: that would coach the response. Compare participant reasoning to a separately adjudicated evidence key afterward.

## Equipment-pilot intake

Complete this with the data owner; unknowns stay blank. No contact messages or data requests have been sent by this task.

| Required agreement | Response |
|---|---|
| Equipment family, operating regimes and reviewing owner | |
| Engineering decision supported and current review method | |
| Sensor names, units, calibration and actual sampling/cycle meaning | |
| Documented failure definition and label provenance | |
| Number of eligible complete, distinct histories; repeated assets/rebuilds | |
| Missing values, flat readings, duplicate cycles and exclusions | |
| Useful warning window and practical intervention time | |
| Fault types, sizes, onset and duration grounded in observed problems | |
| Detection/alarm limits and rationale; cost of misses and early alarms | |
| Fresh reserved-history ownership and exposure policy | |
| Data permission, access, retention and optional AI context | |
| Review success criteria and planned evidence export | |

Current ingestion requires integer operating cycles, unit spacing, numeric sensors and complete failure histories; minimum 25 histories leaves only five for development after the reserved 20. That minimum is not a sufficient study-size justification. Timestamps, healthy-only logs and censored histories are unsupported by this protocol. Resolve that mismatch before ingesting; never invent failure labels. Follow [PILOT.md](../PILOT.md) and the [evaluation protocol](sidekick-engineer-evaluation.md) before any real training or one-time validation.

Until the intake is complete, stop at evidence review. Do not fill agreement fields from assumptions or claim default demonstration limits are suitable for the equipment.

## First-time-user session

Use a disposable workspace and synthetic fixtures, with live AI disabled. Give the user the goal, not click instructions. Let them think aloud; help only when stuck and record the help. Obtain the participant's agreement before recording. Do not collect credentials, contacts or identifying field data in screenshots.

| Task | User goal | Observable completion |
|---|---|---|
| 1. Understand the app | Explain what Sidekick tests and whether a pass approves deployment. | Sensor-fault warning robustness is understood; test evidence is distinguished from field approval. |
| 2. Prepare data | Attach a supplied synthetic CSV and review its mapping; stop before training. | Correct equipment/cycle/sensor roles, failure-label confirmation and readiness understood; upload and setup can be resumed. |
| 3. Interpret failure | Inspect the recorded lr2 result and propose a justified next check. | Failed dropout case, detection denominator and development scope identified. |
| 4. Compare models | Compare aug3 and lr2 and choose the next evaluation step. | Passing limits are distinguished from causal superiority and deployment. |
| 5. Inspect timing | Find a stored warning in replay and explain when it counts. | Scores/active warnings and the useful window are distinguished; missing records are not guessed. |
| 6. Organize and return | Rename/move a fixture item, then reopen it after refresh. | Library organization and direct evidence links work; ready uploads are distinguished from completed runs. |
| 7. Preserve findings | Prepare a regular review brief, edit, save and export it. | Saved draft state and export understood; recorded evidence remains separate. |

Replay mode intentionally lacks uploads, training, library runs and live AI. Use it for tasks 1, 3–5 and recorded reports; use the isolated full workspace for upload/library/brief tasks. Do not record absent replay capabilities as broken full-mode controls. Do not press Train, Freeze or Evaluate during a preparation-only session.

For each task record success, help requested, wrong turns, misunderstood labels, exact words, review time and any waiting time. Do not infer frustration, comprehension or speed from an automated browser run. Prioritize a change when a misunderstanding affects the decision or repeatedly prevents completion; retest that task after the change.

Copy this sheet for each participant:

```csv
participant_alias,date,task,success,help_required,wrong_turns,critical_misunderstanding,review_seconds,waiting_seconds,participant_quote,next_fix
```

The latest automated regression checks and AI browser walkthrough are technical evidence only. Real user observations and field performance remain separate milestones.
