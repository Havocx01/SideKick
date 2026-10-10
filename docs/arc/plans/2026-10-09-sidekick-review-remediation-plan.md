# Sidekick review remediation plan

**Source:** [Full council review](../audits/2026-10-09-sidekick-council-review.md), findings F1–F14.  
**Goal:** Make Sidekick reproducibly buildable, reject invalid study inputs before work begins, recover saved analysis reliably, and complete focused UI/operational fixes.  
**Stack:** Python/FastAPI/SQLite, pytest/Ruff; React/TypeScript/Vite, npm, Playwright and Node protocol tests.  
**Planned at:** `046a972`.  
**Status:** DONE (technical remediation); Docker runtime environment-blocked, changes uncommitted and undeployed.  
**Assurance:** Guarded for data admission, exposure and stored analysis compatibility; standard for UI/deployment fixes.  
**Rationale:** Changes affect the validity of comparisons, one-time validation safeguards, saved user drafts and mode/ownership boundaries.  
**Format:** Repository-specific plan. The installed Arc detail skill lacks its supporting references and document-reviewer files; this document does not claim formal Arc schema validation.

## Scope and defaults

- Address all 14 review findings, including the verification gaps grouped under F2.
- Preserve Sidekick's compact visual identity, existing Cult/Arc adaptations, blue accent, status colors, routes, browser history and report/evidence links.
- Choose **rejection of exact duplicate histories**, rather than deduplicating them silently or inventing new equipment groups.
- Choose **unit-spaced operating cycles** for new experiments. Do not resample, interpolate gaps or change the meaning of recorded cycles.
- Check training feasibility against the **resolved protocol and actual grouped folds**, before creating a job or marking any history exposed.
- Keep analysis and review-brief reuse. Refreshing status must never implicitly start paid work.
- Add public-demo storage safeguards without daily/session AI usage allowances.
- Preserve stored evidence, original names, archived items and saved brief edits. Existing source-compatibility guards remain in force: backend changes may require a new development run before freezing/validating; do not rewrite old source fingerprints to bypass that guard.
- No broad redesign, new model default, live monitoring, censored-history support, nested folders, remote full-mode sharing or automatic deployment.

Planning executes no jobs. Implementation verification uses temporary workspaces, mocked providers and fixture records. The final explicitly marked integration test may train/freeze/score **synthetic fixtures only**, never the user's datasets. Real equipment scoring and paid AI evaluation are separate milestones described below.

## Work sequence and ownership boundaries

| Slice | Findings | Depends on | Main outcome |
|---|---|---|---|
| 1. Restore verification | F1, F2 | None | Generated contract and existing tests become reproducible. |
| 2. Protect data admission | F3, F4, F5, F6 | Slice 1 | Invalid inputs fail before reservation/exposure; valid custom timing works. |
| 3. Restrict Docker exposure | F7 | None | Local full mode is published only on host loopback. |
| 4. Recover and version analyses | F8, F13 | Slice 1 | Existing jobs recover; cache identity tracks model/prompt while drafts survive. |
| 5. Bound demo storage | F9 | Slice 4 | Aggregate storage is bounded without routine AI allowances. |
| 6. Complete UI regression fixes | F10, F11, F12; F2 browser gap | Slices 1 and 4 | Reduced motion, useful result identity, accurate dates and file-browser coverage. |
| 7. Reduce initial payload | F14 | Slice 6 | Measured reduction through selective loading, preserving behavior. |
| 8. Close verification and document usefulness | All; product milestone | Slices 1–7 | Fresh reproducible gate plus an executable engineer/AI evaluation protocol. |

Treat each slice as a reviewable change. Do not mix dataset admission changes with UI redesign. Contract generation is shared ownership: regenerate only after the slice's backend schema changes are settled. No commits, pushes or deployments are implicit in this plan.

## Observable seams and test strategy

| Seam | Verify through | Existing coverage / planned addition |
|---|---|---|
| Public schema generation | Generated output versus checked-in file; TypeScript compilation | `scripts/generate_types.py`; new `tests/test_generated_types.py` |
| Dataset confirmation and run admission | Existing confirmation/create endpoints, `Jobs.create`, profiler findings | `tests/test_uploads_and_modes.py`; new `tests/test_training_admission.py` |
| Exposure transaction | `Workspace.expose` and persisted operation/exposure rows | `tests/test_exposure_and_jobs.py`, `tests/test_worker_lifecycle.py` |
| Analysis lifecycle | Existing start/get/cancel/brief/export APIs and rendered dialog | `tests/test_assistant_api.py`; new `frontend/tests/analysis-recovery.spec.ts` |
| Library behavior | Existing library APIs and visible file-browser controls | `tests/test_experiment_library.py`; new `frontend/tests/library.spec.ts` |
| Result naming | Existing experiment GET response plus result heading/context | Library/API tests and new `frontend/tests/ui-regressions.spec.ts` |
| Motion preference | Render under reduced motion and change preference during the session | `ui-regressions.spec.ts`; actual final numbers and static decoration |
| Build/loading | Production assets, import boundaries and cold-load navigation | New `scripts/check_frontend_payload.mjs`; browser regression checks |

Use API/behavior assertions rather than private CSS classes when practical. Shared test fixtures may seed temporary library metadata and fake completed records, but must not bypass production access controls. Distinct histories in fixtures need genuinely distinct readings; assigning new IDs to the same readings is exactly the case being rejected.

## Slice 1 — Restore verification

**Files:** `scripts/generate_types.py`, `frontend/src/api/types.ts`, `tests/test_pilot_review.py`, `frontend/tests/workflow.spec.ts`, `frontend/package.json`, new `frontend/eslint.config.mjs`, `frontend/package-lock.json`, `.github/workflows/verify.yml`, `TESTING.md`, new `tests/test_generated_types.py`.

1. Add the public library models to generator roots, including request inputs and all nested references needed by the API client. Regenerate the entire output and remove manual interfaces from the generated file.
2. Make generation testable with an optional output path or pure render function. Keep the default command/output path valid. The regression compares a temporary generated file with committed types without overwriting the repository during pytest.
3. Build the pilot fixture from a valid `ExperimentRecord` with an explicit fixture creation date and required configuration/provenance fields. Preserve the production creation-date requirement.
4. Replace the stale `.analysis-source` browser assertion with a semantic assertion of the selected evidence context. Keep the requirement that comparison/brief/replay uses the correct development evidence.
5. Add a minimal frontend correctness lint gate, using ESLint's TypeScript-compatible flat configuration. Enforce runtime/control-flow correctness and focused React rules; avoid broad style reformatting or indiscriminate suppressions. Generated/vendor adaptations should have intentional boundaries.
6. Keep generation consistency, frontend lint, typecheck and build in CI. Distinguish historical verification notes in `TESTING.md` from new results; never replace failed checks with a claim that they passed.

**Acceptance:** Two consecutive generations are byte-identical and retain library exports. Generated output compiles. The 12 pilot tests execute rather than failing at setup. The affected evidence browser test passes with providers disabled. Frontend lint/typecheck and Python Ruff pass.

**Risk:** Generation exposes other contract drift. Resolve it in the generator or client according to backend truth; do not restore manually inserted interfaces as a workaround.

## Slice 2 — Protect data admission

**Files:** `backend/app/data/profiler.py`, `backend/app/experiments/datasets.py`, `backend/app/experiments/jobs.py`, `backend/app/experiments/protocol.py`, `backend/app/experiments/exposure.py`, `backend/app/experiments/store.py`, `backend/app/models/train.py`, `backend/app/experiments/worker.py`, new `backend/app/experiments/preflight.py`, `tests/test_uploads_and_modes.py`, `tests/test_exposure_and_jobs.py`, `tests/test_protocol_and_metrics.py`, new `tests/test_training_admission.py`.

### Duplicate identities — F3

- Reuse the existing history identity algorithm; do not change the identities already stored in the exposure ledger.
- Detect collisions between equipment histories before splitting/admission. Report the affected equipment IDs and explain that repeated readings cannot count as independent histories. Never quietly drop rows or select a preferred duplicate.
- Reject duplicate identities inside a reserved batch in `Workspace.expose`, within the existing transaction, before recording exposure or changing the validation operation. Retain all previously exposed checks.
- New run admission rechecks previously confirmed uploads, so old confirmed metadata cannot bypass the new guard. Historical reports remain readable and are not recalculated or retrospectively stamped invalid.

**Examples:** 60 IDs with identical traces are rejected; renamed/sensor-renamed copies are caught according to the existing identity definition; distinct traces pass; a duplicate reserved batch inserts no exposure rows and leaves `exposure_started_at` unset.

### Fold feasibility — F4

- Validate the resolved split from `check_coverage`, with the resolved protocol's labels and feature warm-up. Check every training fold for nonempty scorable samples and both classes; check validation folds for nonempty scorable samples without imposing an unnecessary two-class requirement there.
- Run the check before `Workspace.reserve`, output directory creation, worker launch or development exposure. Reuse the same checker defensively at the worker boundary for jobs already queued under earlier code.
- Error copy identifies the fold and missing class/sample condition and asks for suitable complete histories or valid timing. Do not silently change the seed, folds, reserve size or label horizon until a combination passes.
- Do not inspect reserved labels to choose models or thresholds. Identity and continuity checks are structural; class feasibility applies to development folds.

**Examples:** The audit's 26-history/seed-0/onset-20 fixture fails before reservation; positive-only, negative-only and empty scorable folds fail; a valid varied-lifetime dataset passes. Rejection creates no experiment, no active worker and no exposure entry.

### Augmentation bounds — F5

- Replace the hard-coded empty-interval assumption with an explicit training-only supported onset interval. Pass available training-history span into the internal sampler; keep evaluation faults separate from sampled training faults.
- Preserve the existing sampling range for default settings whenever training histories support it. Use `lower = min_useful_lead + 5`; take `support` from the minimum available maximum cycles-before-failure across the eligible training histories; use exclusive `upper = min(max(120, horizon_cycles + 1, lower + 1), support + 1)`. Sample only when `upper > lower`. This retains the original default interval when supported, caps it for shorter histories and permits longer custom windows. Fail in preflight with a plain message if no supported interval exists. If there are no eligible varying sensors, retain the existing no-augmentation behavior.
- Keep sampling deterministic for the same seed/configuration/support. Never consult reserved histories to choose augmentation. Changes apply to new runs and their recorded source/protocol metadata.

**Examples:** Minimum lead 114 and 115; lead 115/horizon 130/boundary 145 with sufficiently long histories; short insufficient histories; no varying sensor; same seed repeats the same sampled faults. Valid long settings produce supported faults rather than `low >= high`.

### Cycle continuity — F6

- Promote gapped/non-unit cycle spacing to a blocker for new experiment admission, through a shared structural check/profile finding. Check sorted cycles within each equipment history. An initial cycle greater than 1 is acceptable if subsequent spacing is 1.
- Preserve ordinary missing sensor readings as their existing missing-value behavior; a missing row/cycle is a different condition.
- Apply the restriction at confirmation and run creation. Show a short explanation beside the existing setup validation errors. Leave legacy evidence/replay available with its recorded limitations.

**Examples:** Cycles `1, 11, 21` fail; `5, 6, 7` pass; missing sensor cells with continuous cycles remain governed by existing missingness limits; historical benchmark values and report links stay unchanged.

**Acceptance for the slice:** All four conditions are covered by admission tests that perform no model fitting. Existing valid uploads/default samples are still admissible. Exposure tests show atomic failure. No historical bundle/fingerprint is rewritten, and source-incompatible frozen artifacts remain blocked by their existing guard.

## Slice 3 — Restrict Docker exposure

**Files:** `docker-compose.yml`, `README.md`, `TESTING.md`; new `scripts/check_local_docker.mjs` only if a repository test cannot validate the rendered Compose config reliably.

- Publish API/web host ports as `127.0.0.1:8000:8000` and `127.0.0.1:5173:5173`.
- Keep the API and web processes listening on their container interfaces; changing them to container loopback would break access.
- Preserve service-to-service communication and existing local URLs. Document that full mode is a local workspace; remote sharing needs a separately designed access boundary.

**Acceptance:** `docker compose config` resolves both loopback host bindings. If Docker is available, inspect port publication and fetch health/UI from localhost in a disposable deployment. Do not expose it remotely for a test. Missing Docker is an explicit verification prerequisite, not a successful check.

## Slice 4 — Recover and version analyses

**Files:** `frontend/src/components/AnalysisProvider.tsx`, `frontend/src/components/AnalysisInspector.tsx`, `backend/app/assistant/service.py`, `backend/app/assistant/store.py`, `backend/app/assistant/schemas.py`, `backend/app/api/routes_assistant.py`, `frontend/src/api/types.ts`, `tests/test_assistant_api.py`, new `frontend/tests/analysis-recovery.spec.ts`.

### Recover the existing job — F8

- Replace record-dependent one-shot polling with a lifecycle keyed to analysis ID and active status.
- Retry transient network/5xx reads after 700 ms, 1.5 s, 3 s and then up to 5 s. After five consecutive failures show a recoverable status message and **Refresh status**, retaining the analysis ID and draft. Reset failure count after a successful read.
- Stop automatic reads on terminal status, cancellation, provider unmount or context replacement. Closing/reopening follows the app's existing saved-job behavior and must not duplicate a request. Prevent late responses from another context updating the current dialog.
- A 404/permission denial is not a transient server failure: explain it and stop polling. Preserve the user's draft where safely possible.
- **Refresh status** uses GET only. **Rerun with AI** remains an explicit forced fresh analysis. Do not cancel a running job simply because its status could not be read.

**Acceptance:** A failed GET followed by completion creates exactly one analysis POST. Extended failures retain a recoverable ID. Refresh, close/reopen and switching into Prepare review brief reuse the same result. Explicit rerun creates one new request. Keyboard focus, draft saving and cancellation remain correct.

### Version result reuse while preserving drafts — F13

- Separate scoped evidence/draft identity from generated-result identity. Normalize Analyze result and Prepare review brief to their shared evidence task as today.
- Result identity includes evidence identity, actual task-specific prompt/tool-output contract versions, mode and configured provider/model when live analysis applies. Keep each completed result's actual returned model/prompt provenance.
- Store a separate optional evidence/draft fingerprint instead of parsing a new multi-part result key with `partition(':')`. Update brief conversion/export paths as well as start/reuse paths.
- On reading legacy records, derive draft identity only from verified legacy evidence/context. Do not reuse an old result under a different current model/prompt; retain human-edited text for the same owner and exact scoped evidence. Leave old saved records readable and do not erase edits during migration.
- Preserve consent revocation, visitor isolation, public expiry and explicit force-rerun semantics. Unedited generated drafts can improve with new analysis; edited drafts require preservation.

**Acceptance:** Same evidence/model/prompt reuses output in both Analyze/Brief directions. Model or prompt changes require a new result. Human edits survive that change but never cross evidence, owner or consent boundaries. Server restart and legacy stored records pass compatibility tests. All provider behavior is mocked.

## Slice 5 — Bound public-demo storage

**Files:** `backend/app/config.py`, `backend/app/assistant/store.py`, `backend/app/assistant/service.py`, `backend/app/api/routes_assistant.py`, `backend/app/experiments/library.py`, `backend/app/experiments/demo.py`, `backend/app/api/routes_library.py`, `tests/test_assistant_api.py`, `tests/test_experiment_library.py`, `README.md`.

- Apply safeguards only to public-demo persistent state. Keep local saved analyses and experiments outside demo expiry/capacity rules.
- Proposed configurable starting limits: **2,000 public analysis records / 32 MiB of reserved analysis payload capacity**, and **2,000 demo folders globally / 100 per visitor**. These are server safety defaults to verify against actual payload sizes, not promised load limits or daily AI allowances.
- Reserve capacity atomically before starting provider work. Account for bounded result and the existing 12,000-character draft allowance so an admitted record can finish and save its draft even when another request fills capacity.
- Use a transaction to prevent concurrent admissions exceeding the budget. Expire eligible old demo records first using the existing retention/visitor lifecycle. Never evict current saved drafts or another visitor's unexpired data just to admit a request.
- At capacity, reject only new admission with a clear temporary-capacity error, before paid work. Existing result reads, exports, cancellation and reserved-capacity updates continue. Folder renaming/removal and item archive/restore remain available.
- Reuse ordinary identical evidence results as already intended. Do not convert an explicit AI rerun into an invisible cache hit or reinstate the old session/daily allowance counters.
- Budget both payload and record count; document that physical SQLite/WAL size also needs monitoring. Avoid unbounded startup reads or opportunistic VACUUM on every request.

**Acceptance:** Small configured test limits demonstrate concurrent atomic admission, rejection before provider calls, expiry recovery, visitor isolation, local-mode exemption and successful completion/editing of admitted records. A legacy store already above the new limit remains readable and rejects new admission until eligible expiry frees capacity. Existing no-daily/session-allowance tests remain meaningful and pass below global storage capacity.

## Slice 6 — Complete focused UI fixes and file-browser coverage

**Files:** `frontend/src/components/Layout.tsx`, `frontend/src/components/cult/CanvasFractalGrid.tsx`, `frontend/src/components/cult/RollingNumber.tsx`, `frontend/src/components/cult/BorderBeamCard.tsx`, its CSS module only if verification finds a gap; `frontend/src/components/ExperimentLibrary.tsx`, `backend/app/experiments/library.py`, `backend/app/api/routes_experiments.py`, `backend/app/schemas.py`, `frontend/src/api/types.ts`; new `frontend/tests/library.spec.ts`, `frontend/tests/ui-regressions.spec.ts`, fixture helpers; `tests/test_experiment_library.py`.

### Reduced motion — F10

- Remove the explicit canvas override. Static grid remains under reduced motion, with pointer/gradient movement disabled and no ongoing animation loop that serves no visual purpose.
- Make rolling numbers render final values immediately under reduced motion. Preserve final accessible text and stable dimensions.
- Verify the border beam's existing CSS suppression instead of replacing working behavior. Also check overview bars, selection transitions and manual replay controls.
- Respond to preference changes during the session, and retain normal Cult animations when motion is allowed.

### Meaningful result identity — F11

- Add an optional read-only `display_name` to the experiment GET response. Resolve it from owner-scoped library metadata using a targeted lookup after the existing access check; avoid fetching the full library for each result page.
- Keep the field nullable/defaulted for legacy records. Do not write it into immutable run/evidence payloads. Library renaming changes only metadata.
- Render `display_name ?? record.name`, with source and evidence partition still clearly identified. Long labels truncate visually and remain available accessibly. Archived direct links retain names.
- Do not filter the existing status API or disrupt completion notifications. Regenerate types after the additive schema change.

### Accurate date label — F12

- Change “Modified” to **Added**, since mixed library entries use run creation/upload registration dates. Preserve newest-first date grouping and unspecified dates for historical uploads.
- Do not add an organizational modification timestamp or reorder items after renaming/moving.

### Fixture-only browser journey — F2 coverage

- Test single/double-click/Enter opening; Ctrl/Cmd toggling, Shift range, arrows and select-all within the bulk limit.
- Test F2/context-menu rename in place; Enter/blur save, Escape cancel, unchanged names, duplicates, failed saves and focus return.
- Test folder create/rename/remove; removal retains data and moves contents to Unfiled.
- Test single/bulk move and archive/restore, active-run rejection without partial application, same-folder drops and failed drops.
- Test native drag start/target/drop, selected versus unselected items, archived-item restrictions and polling stability during drag. Keep mobile menu/tap alternatives.
- Test one external CSV, folder inheritance, unsupported/multiple files, retry/cancel and the existing three-second minimum attachment display. No real user files are uploaded.
- Cover date disclosures, search revealing older matches, URL refresh/Back, long names, both themes and 390 px mobile layout. Use seeded records and request interception/stubs for lifecycle states; no real job creation is needed.

**Acceptance:** Existing behavior stays intact, labels align and layout does not overflow. Reduced-motion users see final counts/static effects. Renamed results show the selected experiment's label without evidence changes or cross-visitor leakage.

## Slice 7 — Measure and reduce initial payload

**Files:** `frontend/src/main.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/components/AnalysisInspector.tsx`, `frontend/src/views/Experiments.tsx`, `frontend/vite.config.ts` if manifest output is needed; new `scripts/check_frontend_payload.mjs`, `TESTING.md`.

- Establish an asset/import baseline on the implementation revision; the audit observed 776.92 kB minified / 241.95 kB gzip in the main chunk, not measured startup slowness.
- Split the analysis inspector and overview-only canvas into deferred chunks. Avoid importing those implementations from eager modules through value imports; use type-only imports where appropriate.
- Use the router's existing lazy pattern for setup/progress/library wrapper routes when it materially reduces the eager experiment module. Ensure saved analysis remains in a persistent provider and navigation does not remount it unexpectedly.
- Limit font imports to the subsets actually used, preserving the supported script/fallback behavior. Do not add a bundle visualizer dependency unless native build/import information is insufficient.
- Provide theme-consistent loading boundaries with stable space, no duplicated live regions and no flash of an empty analysis dialog.
- Record raw/gzip **initial route dependencies**, not only the renamed main chunk. Compare identical cold-load and first-action conditions; a new chunk that eagerly preloads is not a win.

**Acceptance:** Initial transferred JavaScript decreases, the removed features load when needed, and first analysis opening/navigation does not regress materially in the measured comparison. All routes, history, saved briefs, reduced-motion behavior and Cult effects still work. Record the actual before/after; do not claim an arbitrary latency target was achieved without measuring it.

## Slice 8 — Fresh closeout gate and usefulness milestones

**Files:** `.github/workflows/verify.yml`, `TESTING.md`, `PILOT.md`, new `docs/sidekick-engineer-evaluation.md`; update the plan state with actual results.

Run affected tests after each slice. Run the complete relevant gate once against the final implementation rather than repeatedly launching the full pipeline during every small edit.

### Automated and browser closeout

1. Ruff and all non-integration backend tests with live AI disabled.
2. Generated types match the checked-in file and generation is idempotent; lint, TypeScript, protocol tests and production build pass.
3. New fixture-only library/recovery/UI tests and existing read-only evidence, walkthrough and investigation tests pass with external provider requests blocked.
4. In a fresh temporary workspace, run the existing **marked synthetic** train/freeze/validation/export integration test. Then run the separately identified synthetic browser workflow if needed to cover the final cross-layer result path. Never operate on the owner's workspace or reuse its exposure ledger.
5. Check Docker publication using available Docker tooling. Record any missing environment prerequisite explicitly.
6. Confirm historical evidence bytes/identifiers, replay/report links, archived direct links and mode restrictions remain unchanged. Confirm source-mismatched frozen validation still fails, active-run archive remains atomic, and saved human briefs survive restart and cache upgrades.
7. Review desktop at 1280×720 and mobile at 390×844, both themes, normal/reduced motion, keyboard operation and representative failure messages.
8. Update `TESTING.md` with exact commands/counts and unresolved limitations; do not reuse the audit's counts as new results. Capture the final diff and source revision for review. Do not deploy automatically.

Representative PowerShell commands, adjusted to the installed repository environment:

```powershell
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
$env:SIDEKICK_ASSISTANT_LIVE_EVAL = '0'
$env:SIDEKICK_MLFLOW = '0'
.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv/Scripts/python.exe -m pytest -q -m 'not integration'
.venv/Scripts/python.exe scripts/generate_types.py
# Compare regenerated output to the intended final types; repeat generation to prove idempotence.
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Push-Location frontend
try {
    npm run lint
    npm run typecheck
    npm run test:protocol
    npm run build
    npx playwright test library.spec.ts analysis-recovery.spec.ts ui-regressions.spec.ts
} finally { Pop-Location }
# This command exercises synthetic model work in test-owned temporary state only.
.venv/Scripts/python.exe -m pytest -q -m integration tests/test_local_workflow.py
```

`npm run lint` and the new spec files were created and passed during this implementation; see the final receipt below. Browser installation is a prerequisite when absent. A plain `git diff --exit-code` during an uncommitted implementation also sees intentional regenerated changes: use the temporary-output comparison until changes are committed, then retain CI's clean-generation diff gate.

### Engineer and AI usefulness evaluation

- Prepare a concise evaluation sheet now: one equipment family, named reviewing engineer, review decision, baseline procedure, independent-data policy, warning/fault settings, failure-label checks and decision consequences.
- Use the existing offline assistant rubric for investigate/compare/warning/data/brief coverage. Keep safety requirements absolute: verified claims, no invented numbers, no causal diagnosis or deployment approval, correct scope, preserved evidence and no job launch.
- Define an engineer comparison of manual evidence review, deterministic analysis and AI-assisted analysis. Counterbalance case/order where possible to reduce learning bias. Measure misunderstandings, useful next checks, missed relevant cases and review time. Require a specific decision benefit, not merely more fluent prose.
- Real equipment histories, review participation and authorized one-time scoring remain external prerequisites. Paid AI evaluation additionally needs an explicit provider/model and spending cap. Do not use a discovered API key or run `--live` automatically.
- Keep model selection unchanged until measured evidence warrants it. Report pilot/AI evaluation as **not conducted** until it actually occurs. Technical remediation can complete independently; field utility cannot be certified by passing synthetic tests.

## Coverage ledger

| Finding | Planned resolution | Completion evidence |
|---|---|---|
| F1 | Generator owns library types | Temporary generation diff + compile + CI generation check |
| F2 | Valid pilot fixtures, semantic assertions, lint and library browser coverage | Passing affected suites and final gate |
| F3 | Duplicate identity rejection and atomic reserved-batch guard | No-fit confirmation/admission/exposure fixtures |
| F4 | Per-fold scorable/class feasibility | Rejected audit fixture with zero reservation/exposure |
| F5 | Supported deterministic augmentation interval | 114/115 and long/short support tests |
| F6 | Block non-unit cycle spacing for new work | Continuous/gapped input and legacy-read tests |
| F7 | Loopback Docker host ports | Rendered Compose config and available runtime inspection |
| F8 | Recover same job ID; distinguish refresh/rerun | Faulted GET test with one POST |
| F9 | Atomic demo capacity and retained edits | Capacity/concurrency/expiry/isolation fixtures |
| F10 | Respect reduced motion | Static grid/final counts, preference-change/browser checks |
| F11 | Scoped visible display name | Renamed/archived/legacy/cross-owner route tests |
| F12 | Accurate Added date label | Rename/move do not alter date/order |
| F13 | Separate result version and draft identity | Model/prompt/legacy/consent/restart tests |
| F14 | Defer measured eager payload | Total initial asset before/after + route/first-action checks |

## Implementation state

- Execution base: 046a972; tracked baseline fingerprints in output/remediation/baseline.json
- Pre-existing dirty paths: docs/arc/ (prior review, this plan and index); excluded from implementation-source evidence
- Declared task paths: files enumerated under slices 1–8; new scoped tests/helpers listed there
- Commit posture: leave changes uncommitted; no commit, push or deployment authorized
- Current slices: none — all technical slices and follow-up reliability corrections are complete
- Completed slices: 1–8; slice 3 runtime is environment-blocked, with rendered configuration verified
- Verification results: generator/pilot 16 passed; admission/exposure/upload/protocol/worker/library 54 passed with scoped Ruff; frontend lint/typecheck passed; affected comparison/warning/brief browser check passed; Compose loopback configuration passed
- Implementation review: completed by the three-member council; [current review](../audits/2026-10-09-sidekick-current-review.md) records R1–R4 lifecycle/consent defects and R5 browser verification failures
- Previous review gate (historical, before reliability fixes): 174 backend tests passed (1 integration test deselected); Ruff, generated types, frontend lint/typecheck, 7 protocol tests and build passed; new fixture browser gate 15 passed/5 failed; existing investigation reopen case failed on stale POST expectation
- Final closeout: passed — 199 backend tests (including integration), 65 browser tests, 7 protocol tests, 12 offline assistant cases; Ruff, lint, TypeScript, generated-type consistency, production build, evidence checks and loopback configuration pass. Source target SHA256: `2b78bd9c02eb06afd2c6280003d81df41027974edcf03f9a9b40a6c55b24d8c2`. See [reliability completion](2026-10-09-sidekick-reliability-completion.md) and `TESTING.md`. Docker runtime and new hosted-memory verification require the unavailable engine.
- Commit posture at completion: worktree only, one reset away from loss; no commit, push or deployment
- Paid AI evaluation: [minimal user-authorized two-case live/local probe](../audits/2026-10-09-sidekick-live-ai-priorities.md) conducted before further fixes; 8 requests, estimated $0.0037048. No added essential conclusions observed, with one weaker visible next check. Broader/engineer evaluation remains unperformed.
- Real engineer pilot: not conducted; engineer/data/protocol prerequisites required

## Decision log

- Planning defaults: reject duplicate identities and cycle gaps; preserve source/exposure safeguards and edited briefs; use Added for dates; retain current AI model and visual identity.
- Demo capacity values above are proposed safety defaults. Verify against bounded payload sizes and the hosted resource envelope before finalizing; keep them configurable and separate from request allowances.
- No product direction requires a pause to write this plan. Real engineer/pilot and paid evaluation inputs are required only when those external studies begin.
- Execution uses the installed implementation skill's slice-ownership and final-review approach. Supporting Arc agent descriptors are absent, so owners receive explicit repository-specific boundaries instead of claiming a formal bundled workflow. Data admission, analysis lifecycle/capacity, and UI/payload work have separate owners.
- Additive result naming uses an `ExperimentDetail` GET response model derived from `ExperimentRecord`; immutable stored record serialization stays unchanged. This satisfies the planned read-only optional field without leaking organization metadata into evidence.
- A pure `backend/app/faults/augmentation.py` bounds helper is added so model fitting and no-fit admission share the same training-only calculation without a circular experiment/model dependency.
- Docker CLI/Compose can render configuration, but the Docker Desktop Linux engine is not running. Runtime port inspection and localhost health/UI verification are environment-blocked; no services were started against the user's workspace.
- Review-brief conversion updates the already-admitted analysis record, retaining its ID and draft identity, instead of reserving a duplicate record. This keeps reads, edits and conversion usable at demo capacity and avoids redundant provider work.
- Fresh council review was read-only for application source. Pending initial-start identity, explicit-save revision guards, legacy cloud provenance and completed-record revalidation need correction before final closeout; browser assertion/harness fixes are also required. Synthetic integration and runtime Docker verification remain outstanding.
- Before further implementation, the user authorized minimal live AI evaluation. The follow-up report contains one consolidated nine-item priority list, preserving R1–R7 and adding specific next-check preservation plus a bounded AI-value concern. No app fixes or model changes were applied by this evaluation; additional paid reruns require a concrete unresolved need.

- The approved reliability completion resolved all nine consolidated technical priorities, including provenance through migration/revocation, access/currency revalidation, pending identity, revision-safe drafts and conversion, concrete fault guidance, bounded fixed AI paths, browser gates, public replay limits and protocol CI. Fresh review defects and stale clarity assertions were fixed. The final one-case live check used five requests (estimated $0.0024564), retained specific dropout guidance and demonstrated essential-information parity, not improved engineer decisions.
