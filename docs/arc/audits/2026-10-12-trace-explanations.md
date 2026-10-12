# Deep explanation refinement — 12 October 2026

Implemented against HEAD `556fc2b72d2d0cf89183adfc08d29b15ab62990c`.
The earlier release-review documents and browser selector repair are retained.

## Result

New explanations must select a private, server-checked trace basis and cite the
matching fault pattern and history. Complete, all-valid recorded useful windows
distinguish no crossings, crossing streaks shorter than the recorded opening rule,
and sustained crossings without active warnings. Streaks include earlier recorded
context using the scorer's valid-reading convention. Sparse displayed samples do
not substitute for full recorded summaries; incomplete, invalid or active windows
do not receive these whole-window bases.

The provider must discuss the selected condition qualitatively, within the selected
history's scope. Unsupported explanations are omitted independently while valid
diagnostic questions remain. No crossings cannot be attributed to persistence alone;
isolated crossings do not prove broken persistence. Some below-threshold scores remain
compatible with intermittent crossings; a claim that all scores remained below does not.
These are bounded safeguards, not a complete semantic proof of every generated sentence.

Sidekick supplies tentative titles such as **Possible reasons for short score-crossing
streaks**. Raw provider titles cannot overwrite them. Public/stored report types remain
unchanged. The facts panel prioritizes the leading explanation's directly cited history,
then the check's direct citation, then related examples; it no longer pairs an explanation
with a different history merely because both share the same fault pattern.

Prompt version: `sidekick-deep-v19`. One structured provider request, no retries,
existing consent/admission checks and development-only scope remain. Historical reports
remain stored and readable; opening them does not automatically buy a replacement answer.

## Verification

- Fresh final affected backend gate: **150 passed**, including actual captured packets,
  missing/wrong trace selections, incomplete records, distinct trace conditions, tentative
  titles and mocked admission → reuse → brief → save → export with one provider dispatch.
- Broad backend gate before the final wording regression: **423 passed, 1 skipped,
  3 integration checks deselected**. Earlier full run: **425 passed, 1 skipped**, including
  the isolated synthetic workflow. User experiment stores and the running user server
  were not changed.
- **22 deep browser checks passed**, covering mobile/desktop, both themes, permission,
  saved reuse, draft context, partial explanations and direct-history selection.
  The first run's two new failures used the stale built frontend; rebuild and complete
  rerun passed without weakening assertions.
- Ruff, frontend lint, TypeScript/production build, **7 protocol checks**, generated-type
  byte consistency and diff whitespace checks passed. Existing dependency deprecations
  and the Vite large-chunk advisory remain.
- Bundle SHA-256: `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`.
  Replay supplement: `3f3092bf6e8ba1d965ca275e3581082c0ee90a38ab44a5c5ee9e460201cd1166`.
  Original paid capture files were not edited.

## Usefulness limit

**Zero paid requests in this change.** Offline review at
`output/trace-explanations-20261012/evaluation/` preserves the original packets and
answers. The two v18 trace captures keep their safe questions but their generic
explanations do not qualify as fresh v19 admission. Other historical contracts are
identified as historical review, not new-generation successes.

Mocked trace-specific answers pass; no fresh paid output or real engineer decision
time was measured. This improves the evidence contract and presentation, but does
not establish that current live AI is consistently better than regular analysis.
Changes are uncommitted and undeployed. Restart Sidekick's API for the updated prompt;
existing historical answers are preserved and are not automatically regenerated.
