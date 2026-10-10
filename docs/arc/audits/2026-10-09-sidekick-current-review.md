# Sidekick: current implementation council review

Date: 2026-10-09  
Base: `046a97240e852c8818d5da6baaccd5a4e5a88cae`, plus the current uncommitted remediation implementation  
Scope: evidence/data admission, experiment workflow and library, analysis/brief lifecycle, privacy, frontend, tests, payload and deployment configuration  
Method: three independent Codex council members, anonymized peer review by all three, and chair verification. Members used the available Codex model; no external council provider or model API was called.

This report reviews the implementation after the [baseline council review](2026-10-09-sidekick-council-review.md). It does not replace that report or certify completion of the [remediation plan](../plans/2026-10-09-sidekick-review-remediation-plan.md). The baseline report was preserved unchanged.

## Verdict

Sidekick is substantially stronger than the baseline. Generated contracts now reproduce, backend checks pass, data admission rejects several misleading or untrainable inputs, and analysis recovery no longer immediately creates a replacement job after a transient status error. Its compact visual identity and evidence-first workflow are worth preserving.

The remaining priority is reliability of analysis and saved briefs. There are four supported lifecycle/consent defects below, including two directly reproduced browser races and an independently reproduced migration/revocation failure. The browser verification gate is also unfinished. These need correction before calling the implementation plan complete.

The product is credible as a local evidence workbench and controlled demonstration. Passing recorded/synthetic checks does not establish performance on an engineer's equipment, improved engineering decisions, or incremental benefit from live AI. The next product investment should be a bounded engineer comparison after the reliability fixes, rather than additional effects or features.

## Priority findings

### R1 — P2: hiding an analysis during its initial request cancels it and loses its identity

**Trigger:** open analysis, close it while the start POST is pending, then reopen after the response arrives.

`AnalysisProvider.tsx:88` increments the generation on close. The initial response subsequently reaches the stale-generation branch at lines 132–133, which cancels a returned active job and does not retain its ID. Same-context reuse at lines 113–116 only helps once a record has already been received. The comment saying close only hides the job therefore does not describe this edge case.

The chair delayed a mocked start response, closed the inspector, released a running record, and reopened it. The probe observed **two starts and one cancellation**. No provider was called. Existing recovery coverage closes after receiving the ID and misses this gap. In a live session, cancellation may occur after provider work has begun; another start can waste work or usage.

**Correction:** track pending context/request identity independently of inspector visibility; retain the admitted ID when a same-context inspector is hidden. Reserve cancellation for explicit Cancel or a deliberate context replacement. Add a delayed-initial-response regression proving hide/reopen retains one job.

Evidence: `frontend/src/components/AnalysisProvider.tsx:88,113,132`; isolated chair probe `output/current-review/race-probes.mjs` and `race-probes.json`.

### R2 — P2: Save draft can acknowledge older text over a newer edit

**Trigger:** click Save draft, continue typing before its response returns, then receive the older acknowledgement.

The inner `writeBrief` completion checks text equality, but `saveBrief` at `AnalysisProvider.tsx:210–212` subsequently updates the record using only generation and record ID. That outer update bypasses the text guard. `AnalysisInspector.tsx:50–51` accepts the old saved text because its saved timestamp is present; its Save callback at line 88 also unconditionally marks the draft saved. The textarea remains editable during the request.

The chair entered newer notes while the older explicit save was delayed. After releasing the response, the editor displayed **Earlier engineer notes**, showed **Saved**, and enabled export. A queued autosave can preserve newer text on the server, so this is not a claim that all newer edits are permanently erased. It is a verified visible reversion and incorrect acknowledgement/export state.

**Correction:** identify draft revisions and apply an explicit save acknowledgement only to the revision it saved. Derive Saved and export availability from acknowledgement of the current revision. Cover typing during save, queued autosave, close/reopen and delayed failures.

Evidence: `frontend/src/components/AnalysisProvider.tsx:72,210`; `frontend/src/components/AnalysisInspector.tsx:50,85,88`; chair browser probe cited under R1.

### R3 — P2: legacy migration removes provenance needed by consent revocation

**Trigger:** upgrade a saved AI analysis whose result uses the old schema, revoke consent, then rebuild analysis for the same owner and evidence.

`AssistantStore.upgrade` at `store.py:59` discards the old result while retaining the brief. `revoke_results` at line 162 clears a brief only when a surviving result identifies its mode as AI. `AssistantService.create` at `service.py:107–112` can then carry the provenance-free draft into a new evidence-only analysis.

An independent council member reproduced this with a temporary store. The chair repeated it using an isolated, fabricated AI-mode record and an incompatible legacy result, without contacting a provider. After migration and revocation: result absent, consent false, brief retained. The newly created **evidence** record inherited the retained cloud-derived brief.

This violates the app's revocation behavior within the same owner/evidence scope. No cross-visitor leak or new external transmission was demonstrated.

**Correction:** preserve cloud provenance separately from the versioned output schema. Apply revocation to retained text even after result migration. Define how edited cloud-derived drafts are treated and add a combined migration → revocation → reuse test; the current separate tests miss their interaction.

Evidence: `backend/app/assistant/store.py:59,162`; `backend/app/assistant/service.py:107`; chair `output/current-review/legacy-consent-probe.py` and `.json`.

### R4 — P2: reopening a completed analysis bypasses server revalidation

The same-context shortcut at `AnalysisProvider.tsx:113–116` returns the completed in-memory record without refreshing it or its capabilities/consent. Polling at line 139 only covers active jobs. If access or consent changes elsewhere, the inspector can reopen displaying stale AI output and a saved brief even though a server read would replace/reject them. Demo expiry has the same client-cache gap. Model/prompt updates can also remain stale until reload or explicit rerun.

This is source-verified by the chair and peer reviewers, not a separate browser reproduction. Another-tab consent revocation currently requires the API: the inspected frontend has no caller that disables consent. The issue is continued client display/access enforcement, not a newly demonstrated cross-owner disclosure; revocation cannot undo an already downloaded document.

**Correction:** revalidate ownership/access/expiry when reopening without automatically running paid analysis. A GET/capabilities refresh covers access, but GET alone does not establish current model/prompt identity: the server currently serves historical records. Provide a safe currency check or explicitly identify historical cached output. Keep admitted active-job recovery separate from completed-result freshness.

Evidence: `frontend/src/components/AnalysisProvider.tsx:113,139`; `backend/app/api/routes_assistant.py:98–120`; result identity logic in `backend/app/assistant/service.py:57–73`.

### R5 — P2: the browser closeout gate is still red

Fresh fixture-only `library.spec.ts`, `analysis-recovery.spec.ts` and `ui-regressions.spec.ts` execution: **15 passed, 5 failed**. All six recovery tests passed. Four desktop/mobile library theme checks and the renamed archived result context check passed.

The five failures need test corrections and another complete run; they should not all be labelled product defects:

| Failure | Evidence and interpretation |
|---|---|
| Row selection after opening a context menu | Base UI hides the background accessibility tree while its menu is open; the role locator cannot find that hidden row. Assert retained selection without assuming background accessibility. |
| Archive drag journey times out | The helper dispatches dragend on a row locator after drop can remove that row. Locator retry can consume the test timeout before Archive is clicked. The snapshot already shows a successful archive; native drag completion still needs proper coverage. |
| CSV validation alert assertion | Two alerts exist after successive invalid drops; a broad role locator is ambiguous. Scope attachment/global errors and verify stale-error behavior deliberately. |
| Upload setup heading | Navigation reaches the correct existing setup URL, but the test expects New experiment; the actual upload heading is Use your equipment histories. |
| Reduced-motion transform | The assertion expects an identity matrix; the computed value is none, which also represents no transform. Static canvas, final numbers and hidden beam checks pass before this assertion. Later dynamic preference/replay assertions were not reached. |

A separately executed existing investigation reopen test also failed with a **25-second timeout**: its helper waits for a POST on every reopen, while the new client reuse shortcut sends none. The similar brief-first test has the same source mismatch but was not executed in this review. Update tests to verify visible output, job identity, persistence and request counts without depending on obsolete network behavior. Add regressions for R1–R4 so a green gate has meaningful coverage.

Evidence: `frontend/tests/library.spec.ts:49,107,140,178`; `frontend/tests/library-fixtures.ts` drag helper; `frontend/tests/ui-regressions.spec.ts:47`; `frontend/tests/investigation.spec.ts:115,123,165–175`.

### R6 — P2, conditional: publicly deploying replay permits unbounded analysis storage

The replay Docker target listens on all container interfaces. Analysis records are admitted with `public=True` only in demo mode (`service.py:118,123`); aggregate caps and expiry apply only to public rows. Repeated deterministic requests to an externally published replay deployment can therefore accumulate permanent records.

The current Render configuration and default Docker target use **demo**, whose new bounds are implemented. This is an additional deployment-mode gap, not evidence that current demo capacity is broken or that the explicitly demo-scoped remediation failed. It was source/configuration verified, not load-tested.

**Correction:** document replay as private-only, avoid persisting public replay analysis, or give public replay bounded retention. Preserve the intended unrestricted local workspace.

### R7 — P3: CI omits the focused protocol tests

`.github/workflows/verify.yml` runs lint, typecheck, build and `npm test`, but `npm test` only runs Playwright. The separate `npm run test:protocol` command is absent. The seven protocol tests pass locally; add them to CI so protocol helper regressions fail the normal gate.

## What improved and should be retained

- **Input and workflow safeguards:** duplicate content identities, non-unit cycle spacing, actual fold scorable/class feasibility and augmentation support are checked before training admission. Reserved duplicate rejection is atomic; legacy exposure reconstruction remains readable. These are substantive improvements over the baseline findings, backed by focused tests and the fresh backend suite.
- **Reproducible contracts:** the generator now owns library and result-detail types, with deterministic output comparison. Pilot fixtures satisfy the current record schema. Frontend lint is installed and passes.
- **Evidence boundaries:** grouped equipment separation, training-only preprocessing, source/frozen-model checks, exposure-before-scoring and scoped evidence remain core strengths. No review finding demonstrates changed benchmark metrics or fitting from reserved predictions.
- **Analysis recovery:** bounded retries, GET-only Refresh status and admitted active-job reuse work in six fresh browser recovery tests. Keep those behaviors while fixing the earlier admission gap.
- **Demo capacity:** transactional record/byte reservation rejects new work at capacity while preserving existing reads, edits and brief conversion. JSON escaping is budgeted; local mode remains exempt. This is storage safety, not a per-user analysis allowance.
- **Naming and organization:** library labels stay separate from immutable experiment names; result detail exposes the scoped display name. Added correctly labels the registration date. Archive/direct-link behavior remains preserved in the design and relevant fixtures.
- **UI:** fresh 1280×720 and 390×844 library screenshots in both themes show a coherent compact interface, distinct ready/completed badges and appropriate mobile folder controls. Long labels wrap without page overflow. Very long labels push later rows below the mobile fold; normal scrolling is appropriate. This review did not freshly inspect every page or perform a complete accessibility audit.
- **Motion and payload:** shared reduced-motion handling and deferred inspector/canvas/routes are worthwhile. Initial JavaScript dropped meaningfully; current main output still triggers Vite's large-chunk advisory. Fix verification and measure real usage before more bundle splitting.
- **Evaluation discipline:** `docs/sidekick-engineer-evaluation.md` separates manual, deterministic and live-AI usefulness, keeps evidence/safety requirements absolute, and records real engineer/data/budget prerequisites instead of asserting unmeasured benefits.

## Verification performed

| Check | Fresh result / scope |
|---|---|
| Backend `pytest -q -m 'not integration'` | **174 passed, 1 deselected**, two existing dependency deprecation warnings. Live AI disabled. |
| Ruff over backend, tests and scripts | Passed. |
| Temporary generated types versus frontend types | Exact SHA-256 match. No substitution of tracked files during review. |
| Frontend lint and TypeScript | Passed. |
| Protocol tests | **7 passed**. |
| Production build | Passed; main JS 654,061 raw bytes / 204,109 gzip estimate; Vite large-chunk warning remains. |
| New fixture-only browser gate | **15 passed, 5 failed**, detailed above. |
| Existing investigation reopen case | **1 failed**, stale POST expectation; bounded to 25 seconds. |
| Cold overview / first analysis payload test | **1 passed**, live provider disabled. Captured requested chunks including the lazy canvas. |
| Targeted race probes | Two browser races confirmed with mocked responses; legacy migration/revocation reproduced without a provider. |
| Local Docker configuration helper | Passed; host API/UI publication is loopback. Docker Desktop Linux engine unavailable, so runtime container verification not performed. |
| Production dependency audit | `npm audit --omit=dev`: zero reported advisories. This excludes dev dependencies and is not a complete security audit. |
| Normal `git diff --check` | Passed. |
| Recorded evidence | Four tracked evidence files match HEAD after checkout line endings are normalized; Git reports no evidence changes. Prior baseline report SHA-256 unchanged. |

The preceding implementation's offline assistant rubric also passed **12 cases** across investigate, compare, warning, data and brief, reporting unchanged evidence and no training jobs. That result checks recorded-evidence explanations and reference discipline; it is not a live-model usefulness study.

Actual cold overview JS: **659,026 raw / 206,504 estimated gzip bytes**, versus baseline **776,972 / 241,964**: approximately **15.2% less raw and 14.7% less gzip**. Includes the canvas chunk requested immediately on overview, rather than claiming all lazy code is deferred indefinitely. One local sample measured overview at 776 ms and first analysis opening at 456 ms; the baseline samples were 797 ms and 439 ms. These samples do not establish a latency improvement. Artifacts: `output/current-review/payload-resources.json` and `.timings.json`; baseline `output/remediation/payload-before.json`.

No application training or reserved-validation jobs, paid AI request, engineer study, commit, push or deployment occurred during this review. Browser servers used test-owned temporary workspaces and were stopped by the test runner. App implementation files were not edited by the council review.

## Closeout and product decision

Fix R1–R4, repair the browser harness/contracts and add focused race/revocation coverage, then rerun the relevant complete gate. The plan's isolated synthetic integration workflow, Docker runtime verification and final `TESTING.md` closeout are still outstanding; this review does not mark them complete. Address R6 only with its public replay exposure clearly understood; add R7 to normal CI.

After technical closeout, run the documented engineer comparison. Ask whether Sidekick helps a reviewer identify weak fault cases and choose useful next checks with fewer misunderstandings or less effort. Then compare deterministic and live-AI analysis on the same tasks. Until that evidence exists, retain the current model rather than treating a model upgrade as a demonstrated improvement.

Council reviewers agreed on the main correctness findings after anonymized peer review; rankings differed. The synthesis prioritizes reproduced behavior and source evidence rather than majority voting. No official Arc scorecard grade or deployment certification is claimed.
