# Sidekick V2 verification

## Backup, startup and engineer pack (10 October 2026)

The local recovery tool uses SQLite snapshots (including WAL), the existing server lock and database writer locks, file checksums, and a new destination only. Focused Windows checks passed **21 recovery tests**, with one native source-symlink test skipped because Windows did not permit creating it. Crafted ZIP symlink and traversal defenses run independently. The fixtures verify IDs, evidence bytes, saved mapping, folder labels, briefs, ownership, cloud provenance, revocation, original public expiry, pilot records and the exposure ledger across recovery/store restart. Environment-file exclusions handle Windows filename casing. An actual `tasks.ps1 verify-backup` / `restore` fixture check passed in the project's OneDrive location; a directory-rename failure led to copy-based publication into the exclusively reserved destination. No user workspace was restored or overwritten. Isolated Linux container checks cover WAL, `flock`, preserved bytes, no-overwrite, uppercase environment-file exclusion and native source-symlink rejection. [Backup usage and snapshot limits](docs/workspace-backup.md).

Moving Select imports out of the shared Chrome module deferred an unused dropdown dependency from Overview. Production cold-route JavaScript fell **663,253 → 575,054 raw bytes** and **208,117 → 177,920 gzip bytes** (14.5% compressed reduction). Measurements count all requested JavaScript, including immediately mounted lazy components. Fixture timings were **791 → 796 ms** for Overview and **349 → 480 ms** for first analysis; these noisy observations do **not** establish a latency improvement. A 610,000-byte actual-response-body budget protects the reduction, and the first deferred dropdown's keyboard/focus behavior is checked. No animation implementation was changed; the three motion checks passed with the payload test. The Vite chunk-size advisory remains visible. Receipts: ignored `output/performance-improvement/`.

The offline engineer packet generator passed **10 focused tests** and produced 12 cases, four synthetic CSVs, separate reviewer and facilitator materials, eight deterministic brief examples and blank score/order sheets. Desktop and 390 px HTML were visually inspected without horizontal overflow. Both review methods link to the same complete CSVs. Alternate bundles must provide an actual dropout detection failure, an early inactive replay point before the first active warning, and a feasible five-point alarm-limit breach; unsuitable contexts are rejected before output. Recorded identifiers and null historical source identifiers remain intact; a bundle SHA-256 identifies the actual input. The facilitator's next-check rubric remains separate from actual local actions and requires engineer adjudication. AI answers and engineer observations are absent. [Generate and conduct the review](docs/engineer-evaluation-pack.md).

Changes remain uncommitted. No paid provider request or real training/reserved-validation job was launched for these improvements. The final gate excludes the marked training integration test and browser training workflow; the unchanged lifecycle tests use sleeping stub workers. The final repository gate and review target receipt are recorded in [the implementation plan](docs/arc/plans/2026-10-09-sidekick-next-improvements.md).

## Docker runtime and commit follow-up (9 October 2026)

The Docker prerequisite is resolved. Docker Desktop's stale runtime socket directory was preserved under `run.sidekick-verification-backup-20261009` and replaced after stopping the failed Desktop processes; no image, container, volume, WSL disk or Sidekick data was deleted to repair startup. Linux Engine 28.3.2 became available.

Fresh demo, replay and development API images built successfully. Isolated Compose services served the frontend, proxied API health and recorded selection on loopback-only ports 15173 and 18000. The final demo image passed the existing hosted-memory script under a 512 MiB hard limit: **266.26 MiB peak sampled working set**, **268.87 MiB cgroup peak**, **7.73 seconds** for the synthetic training/export check, and no OOM kill. Owner isolation and exported evidence were checked. Replay HTTP checks passed record and byte capacity, readable/editable/exportable existing records at capacity, reuse, owner isolation, restart persistence, and expired read/export rejection with capacity recovery. These checks used disposable containers, smaller test limits, no host data mounts and disabled live AI.

The fresh gate passed **212 backend tests**, **68 browser tests**, **7 protocol tests**, Ruff, frontend lint, TypeScript, generated-type consistency and production builds. An initial backend run found Windows CRLF conversion of the generated contract; `.gitattributes` now pins that file to LF without weakening its byte-for-byte test. `.dockerignore` excludes browser traces/reports, which inflated the build context during concurrent tests. Two test-library deprecation warnings and the existing bundle-size advisory remain nonblocking.

The reviewed application and animation changes were already committed in `a807144` and merged into starting HEAD `97b8afd`. This authorized follow-up records the configuration fixes and verification in Git. No push or public deployment was performed. [Runtime receipt and commands](docs/arc/audits/2026-10-09-sidekick-deployment-verification.md) describe the final checked images; detailed local fixtures and memory measurements are under ignored `output/deployment-verification/`. Earlier blocked statements below describe historical checkpoints. Field reliability and measured engineer/AI benefit remain separate, uncompleted evaluations.

## Animation regression follow-up (9 October 2026)

The user's Chrome reported system reduced motion, which the reliability changes newly enforced for rolling numbers and the fractal background. Sidekick now has a persistent app-only Animations switch alongside the theme control. It follows the system until explicitly changed, then applies the same choice to Motion components, CSS transitions, the canvas, border beam and theme transition. The user's existing overview tab was refreshed, enabled and checked again after refresh; Windows and Chrome preferences were unchanged.

The focused browser gate passed **32 tests** across motion, UI regressions, walkthrough interactions and evidence clarity, including both themes and 390 px layouts. The three new motion tests also passed after strengthening the beam assertion to observe its changing angle. They verify actual intermediate rolling-number values and growing bar transforms under both normal and system-reduced motion, cursor-responsive canvas frames, keyboard activation, static opt-out and persistence. Frontend lint, TypeScript and the production build passed. Impeccable's scoped detector returned no findings. The screenshot is `output/playwright/remediation/overview-animations-enabled.png`.

This follow-up is frontend-only and supersedes the earlier motion behavior; the earlier reliability receipt and source manifest describe their original checkpoint. No training, validation job, live AI request, commit or deployment was performed for this fix.

## Reliability and AI completion (9 October 2026)

The final backend gate passed **199 tests**, including the marked synthetic training, freeze, reserved-validation and export integration test. Ruff, frontend lint, TypeScript, all **7 protocol tests**, deterministic generated-type comparison and the production build passed. The complete browser gate passed **65 tests** (3.5 minutes), including the browser sample train/freeze/validate/export workflow. The protocol tests are now part of normal CI; paid evaluation stays outside CI.

Regression coverage includes migration-before-upgrade provenance, scoped atomic revocation, late-write tombstones, retained evidence-only briefs, owner/session/expiry checks, historical output currency, active-job reuse, public replay/demo capacity and legacy byte accounting. Browser coverage verifies delayed admission through close/reopen and analysis/brief switching, GET-only recovery, replaced-context isolation, explicit-save revisions, conversion/save ordering, failed-draft preservation, keyboard selection/rename, drag/drop, CSV retry/cancel and archive links. Desktop and 390 px layouts, both themes and reduced motion were checked. Synthetic jobs use isolated test-owned workspaces, not saved user experiments.

Fresh review reproduced two additional defects: conversion could overwrite concurrently saved notes, and revocation could deny safe export of a retained evidence-only brief. Conversion now shares the client write queue, revision guards retain newer visible text, and the server merges current draft fields inside a SQLite transaction. Evidence-only retained briefs remain exportable with reconstructed local evidence; revoked-record writes stay denied. The independent standards reviewer exhausted its usage after supplying a concrete reproduction; the controller completed both review axes locally. See the [closeout review](docs/arc/audits/2026-10-09-sidekick-reliability-closeout.md) for that limitation.

Earlier full browser attempts found stale walkthrough assertions in addition to the repaired library harness: outgoing Cult previews briefly coexist, compact copy/labels differ, and the sensor matrix is intentionally always expanded. The focused walkthrough suite now passes **11 checks** using the present accessible preview and current semantics. Exact recorded counts, read-only behavior, stored alert state and keyboard disclosures are retained.

All **12 offline assistant cases** pass the expanded usefulness rubric. Mocked comparison, warning and data paths verify local server inspection followed by one structured provider selection request. A single authorized post-change live failing-result analysis used the unchanged current model, five provider requests, zero retries and the six-request/$0.10 ceiling. It took **7.84 seconds**, with estimated usage cost **$0.0024564**, retaining missing-reading flags, median imputation and late/missed-warning checks. This case showed equivalent essential information to local output; improved engineer decisions are **not established**. Outputs and usage meter remain in ignored `output/reliability-live-check/`; no further paid suite was repeated. This new probe is separate from the earlier two-case review.

Recorded data/evidence/submission/artifact content and the original council audit remain unchanged. Existing evidence/source compatibility checks remain active; old source fingerprints are not rewritten to permit validation. Cold overview JavaScript measured **661,348 bytes raw / 207,304 gzip**, compared with **776,972 / 241,964** before remediation. Overview and first-analysis-open fixture timings are recorded separately and are not performance guarantees. The main-chunk size advisory and two Starlette/AnyIO deprecation warnings remain nonblocking.

`node scripts/check_local_docker.mjs` passes the API/web loopback publication check. Docker runtime and fresh hosted-memory verification are **environment-blocked**: `docker info` cannot connect to the Docker Desktop Linux engine pipe. Configuration success is not runtime verification. No deployment, commit or push was made. Real-equipment reliability and the [engineer evaluation study](docs/sidekick-engineer-evaluation.md) remain separate milestones.

Final receipts, manifests and logs are under ignored `output/remediation/reliability-*`. Changes exist only in the worktree and remain uncommitted and undeployed.

## Read-only AI investigation (7 October 2026)

104 non-integration backend tests passed, including bounded provider tool calls, selected-experiment and model scope, verified claims, private packets, consent/revocation, local mapping review, immutable data, reusable briefs and public storage limits. Cloud calls were mocked; no live provider evaluation or paid request was made.

29 browser checks passed on the final workflow build. The sample training, freeze, one-time validation and ZIP export test also passed during this implementation. New checks cover exact fault citations, reusing an investigation in a brief, applying a mapping draft without confirming failures, and mobile layout/focus in both themes. The walkthrough remains read-only. Desktop analysis and review drafts, plus mobile analysis and data review, were visually inspected in light and dark themes.

TypeScript, the production build and Ruff passed. The existing main-chunk warning and test-library deprecation warnings remain. Live model behavior and field usefulness still require separate evaluation. This implementation has not been pushed or deployed.

## Comparison UI refinement (7 October 2026)

Five comparison browser regressions passed, covering model switching, keyboard selection, progressive disclosure, metric scope and fault links. TypeScript and the production build passed. Passing and failing results were visually checked, including light and dark themes. Layouts at 390, 768, 1024 and 1440 pixels had no page overflow. The existing main-chunk size warning remains.

## V2 analysis checks (6 October 2026)

The local backend suite passed 81 tests and the browser suite passed 13. Assistant tests cover the request header, origin and cross-site guards, owner-scoped records and exports, escaped review briefs, invalid candidates, disabled workflows, session and daily quotas, the public evidence allowance (HTTP 429), presenter-code throttling, browser-bound presenter access, timeouts, cancellation, restart recovery, consent revocation and replay mode never calling the provider.

Evidence tests cover detection and burden failures in the same or different cases, missing measurements, deep links to the fault matrix and replay cycle, the comparison overview and unchanged recommendation, unavailable replays and cycles, and the generated brief draft. Provider tests use mocked responses only. The provider receives aliased models and cases with recorded metric values. Interpretations with numbers, links, unknown aliases, cause or deployment claims, or contradictory verdicts are rejected and fall back to recorded evidence.

Browser tests cover the contextual analysis inspector, keyboard focus return, two-model comparison, replay warning explanation linked to the replay cycle, and editing, saving and exporting a review brief. Analysis opens in a centered modal dialog at every width, up to 640 pixels wide, and was checked at 390 and 1440 pixels. Generated API types match the backend. TypeScript, the production build and Ruff passed. The existing bundle-size warning remains.

Live OpenAI behaviour has not been evaluated; run `scripts/evaluate_assistant.py` with a server-side key. The engineer usability comparison against V1.5 has not been run. The V2 changes are local and have not been deployed.

## Previous prototype checks

Checked locally on Windows and in a fresh Linux Docker image:

- 27 backend tests passed. They cover CSV mapping, protocol checks, fingerprints, equipment separation, exposure tracking, paired comparisons, exports, cancellation, timeout and server interruption. The integration test trains a model, freezes it, rejects a modified artifact, then completes reserved validation. A separate run has no qualifying model.
- Eight browser tests passed. They cover the five-step walkthrough without job creation, playback seeking and completion, missing measurements, incomplete coverage, hosted/replay capability flags, inspected-model context, compact layout, keyboard-accessible explanations, the Evidence guide, dark mode, mobile layout, real training, refresh persistence and ZIP filenames. The sample test also freezes the recommendation and scores reserved equipment once.
- TypeScript and the production frontend build passed. Ruff's configured correctness checks passed. Generated API types match the backend.
- The frontend dependency audit reported zero vulnerabilities when checked. The build reports a nonblocking warning about the main JavaScript chunk size.
- A compact hosted sample completed inside a 512 MiB Linux container in 7.58 seconds. Measured peak working set was 241.56 MiB; the cgroup reported a 242.62 MiB total peak. This includes the API server, training worker and measurement process. ZIP contents, reserved-data exclusion and browser isolation also passed.

The resource measurement predates the walkthrough and wording refinements; its recorded source digest identifies that revision. Training and resource settings are unchanged. It is a local single-run check, not a load test or a promise of Render latency. [Recorded measurement](media/submission/v1.5-linux-verification.json).

The recorded walkthrough and report were also checked with external browser requests blocked. All resources came from the local server. Layout checks at 1440, 1152, 960 and 390 CSS pixels found no page overflow; the smaller desktop widths exercise the layout space available at increased browser zoom.

## Equipment pilot checks (6 October 2026)

The local backend suite passed 41 tests, including real training, freezing and reserved evaluation. Pilot tests cover saved agreements, incomplete checks, synthetic classification, agreements after scoring, concurrent exposure checks, mismatched evidence, failed final models, duplicate reviews, optional timings, escaped exports and local-only API access.

A new browser sample completed training, agreement, freezing, reserved evaluation, engineer review and a named ZIP download. Agreement and review survived refreshes and a server restart. The ZIP's review, dataset fingerprint, validation ID and model digest matched its evidence; raw sensor readings were excluded. The pilot layout was checked at 390, 768, 1024 and 1440 pixels in light mode and at desktop width in dark mode, without sideways page overflow. The report also fits at 390 pixels. Eleven browser regression tests passed. These were synthetic workflow checks, not an actual engineer pilot or measured benefit. TypeScript, the frontend build and Ruff passed.

## Run the checks

The 6 October decision-explanation update passed 50 backend tests and 11 browser tests. Regression cases distinguish lowest detection from highest early-alarm time, name the failing fault and limit, handle missing measurements and incomplete coverage, preserve historical evidence, and keep development and final-validation explanations separate. The result, Evidence guide and HTML export use the same recorded reason. TypeScript, the production build and Ruff passed. The existing bundle-size warning remains.

The interface was also checked at 390, 768, 1024 and 1440 pixels and in dark mode. No page overflow was found. [First equipment pilot checklist](PILOT.md) documents the remaining field-data and engineer-review work. No actual industrial pilot or measured field benefit is claimed.

After the README setup and build, use PowerShell from the repository root:

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/generate_types.py
git diff --exit-code frontend/src/api/types.ts
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm run lint
npm run typecheck
npm run test:protocol
npm run build
npx playwright install chromium
npm test
```

While generated types are intentionally uncommitted, use `scripts/generate_types.py --output output/generated-types-check.ts` and compare that temporary output with the intended frontend file; CI retains the clean-generation Git diff check. Two final temporary generations matched the frontend types exactly.

Each browser test invocation creates its own workspace. This keeps tests independent without deleting an existing exposure ledger. On Linux, install the dev requirements, run the same Python checks, then build and test from `frontend`. Use `npx playwright install --with-deps chromium` when browser system dependencies are missing.

The GitHub workflow runs these checks and a separate hosted-memory check. It does not deploy the service.

To repeat the Linux resource check with Docker:

```powershell
docker build --target demo -t sidekick-memory .
docker run -d --name sidekick-memory --memory=512m --memory-swap=512m sidekick-memory
docker cp scripts/check_hosted_memory.py sidekick-memory:/tmp/check_hosted_memory.py
docker exec sidekick-memory python /tmp/check_hosted_memory.py
docker rm -f sidekick-memory
```

The script requires cgroup v2. It checks the hosted sample, its export and browser isolation, and fails if sampled working-set memory reaches 450 MiB.

## Evidence boundaries

The benchmark metrics remain unchanged. The added historical `lr2` replay was checked against 650 original scalar metrics within a tolerance of 0.000000001. Other historical models retain only their original replay examples. These are simulated NASA data, not ABB field results.

New ordinary and augmented XGBoost comparisons match configuration and random seeds. Whole-equipment bootstrap intervals describe measured detection and burden differences. Selection used the same development evidence, so these intervals are exploratory rather than an independent confirmation of augmentation's benefit.

The local exposure ledger detects identical equipment readings despite changes to equipment IDs, sensor names or failure labels. It cannot prove that outside data are unseen, and edited readings or a different sensor subset may not match an existing identity. The user must still confirm that reserved histories were not used for decisions. Deleting the workspace removes the ledger. A failed, cancelled or interrupted reserved-scoring attempt remains exposed once scoring starts.

Frozen artifacts are local trusted files, not an interface for importing arbitrary models. Changing the source, dependencies, protocol or artifact prevents validation against an incompatible frozen record. Exports omit raw sensor readings and the serialized model.

## Remaining before a field pilot

- Agree on warning windows, acceptable alarm burden and representative fault settings with an equipment engineer.
- Obtain complete, representative equipment histories and a separate untouched evaluation set.
- Calibrate faults to actual sensor behavior and check failure labels.
- Evaluate on real equipment and document operating conditions, maintenance costs and missed-warning consequences.

The equipment pilot additions are local and have not been deployed. Hosted uploads, custom protocols, model freezing, reserved scoring and engineer review remain disabled. This version does not monitor equipment, approve deployment or establish field reliability.
