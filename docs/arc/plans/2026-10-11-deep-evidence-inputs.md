# Richer recorded inputs for deep investigation

Status: DONE. Planned/effective assurance: Guarded (cloud data scope, evidence attribution, saved-context identity). One local owner; no subagents. Work remains uncommitted and undeployed. No paid calls, training jobs or reserved scoring.

Implementation baseline: HEAD 3b0d54c951634e09bbe64731635d1f4bc3e6742b with the prior deep/analysis changes retained. Initial source hashes and dirty paths are recorded in ignored `output/deep-evidence-inputs-20261011/baseline.json`. Arc's full workflow references are absent from the installed prompt-only bundle; use bounded local implementation and self-review. Existing Arc Input/Textarea/Button controls are available.

Seams: bounded, aliased supporting evidence computed from stored replay/profile/explanation records; optional recorded preprocessing/fold metadata on newly built bundles; optional user-entered engineer context on deep requests and converted briefs; no raw traces, contact fields, model execution, database migration or automatic regeneration.

<task id="recorded-inputs" kind="behavior" status="done">
<intent>Add paired warning/score summaries, sensor quality, recorded fold variation and feature contributions, with explicit unavailable states, partition checks, source references and bounded provider input.</intent>
<verify>pytest tests/test_deep_evidence_inputs.py tests/test_deep_investigation.py -q</verify>
<done>Exact pairing and evidence scope are tested; historical preprocessing is not guessed; new metadata is captured without modifying scalar results; new inputs affect reuse/currency.</done>
</task>
<task id="engineer-context" kind="behavior" status="done" depends_on="recorded-inputs">
<intent>Provide optional equipment type, sensor meaning and decision fields before deep requests. Preserve context in saved reports/briefs, update disclosure and use existing themed controls.</intent>
<verify>npm --prefix frontend run lint; npm --prefix frontend run typecheck; fixture browser checks</verify>
<done>Empty context is backward compatible, edited context has distinct identity, entered values are explicitly sent and not treated as verified evidence. Contacts and existing pilot free text are never included automatically.</done>
</task>
<task id="closeout" kind="verification" status="done" depends_on="engineer-context">
<intent>Review privacy, input bounds, attribution, lifecycle and UI; run fresh affected gates and document limitations.</intent>
<verify>Ruff; relevant backend tests; generated types; lint/types/build; affected fixture browser suites</verify>
<done>Gates pass, receipt is saved, no paid calls or jobs ran, historical gaps and remaining usefulness evaluation are documented.</done>
</task>

Closeout: prompt v9 includes bounded matched-history outcomes, threshold margins/persistence, recorded preprocessing, sensor quality, recorded fold outcomes and clean-prediction contributions. Supporting records are separately citable and displayed in a collapsed section. Engineer context is explicit, trimmed, bounded and retained across saved deep reports/brief conversion; empty values preserve compatibility. Historical reports retain their IDs and appear historical rather than launching paid regeneration. New bundle metadata is captured from already evaluated objects; historical bundles and scalar metrics are not rewritten.

Local self-review covered exact candidate/partition/threshold/cycle matching, missing score/gap streaks, contribution identity and scope, selected-example bias, full-profile scope, repeat-equipment fold counts, supplemental input bounds, user-context trust/consent, saved-context hashing and legacy reuse. Fixed a score-streak gap issue before closeout. Fresh offline gate: 347 backend tests passed, one skipped and three integration tests excluded; broad Ruff, generated types, frontend lint, TypeScript/production build and seven protocol tests passed. Browser verification covered 36 distinct cases: 35 initially passed; one new asynchronous request-capture assertion was corrected without weakening behavior, and all seven deep cases passed in the targeted rerun. Mobile/desktop, light/dark, focus, entered values, report/review reuse, permission, draft recovery and motion remained covered. Inspected the mobile screenshot. Existing deprecation/chunk advisories remain. Receipt: ignored `output/deep-evidence-inputs-20261011/verification.json`.

Operational note: restart `tasks.ps1 api` to load backend changes. Only new investigations use the enriched packet; saved historical answers remain saved. Historical preprocessing/full fold outcomes remain explicitly unavailable. Actual improvement to engineer decisions requires the separate usefulness evaluation; no provider evaluation was run for this update.
