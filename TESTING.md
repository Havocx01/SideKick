# Sidekick V2 verification

## Default animations and API startup (10 October 2026)

Animations now default to on even when the operating system requests reduced motion. An explicit saved **Animations** off choice still disables movement and survives refresh; this supersedes the system-derived default in the 9 October follow-up. Motion checks observe intermediate rolling numbers, growing bars, cursor-responsive canvas frames and changing border-beam angles. Analysis and manual walkthrough navigation remain usable with motion disabled.

`tasks.ps1 api` now runs a single foreground server, without the development reload supervisor. Reload is explicit (`-Reload`) and watches backend only; `make api` and `make api-dev` match those modes. Startup runs from the repository folder, supports an alternate port and reports failed native exits. The supplied log records a graceful stop of both server and reloader; it does not identify the signal sender. Removing default reload avoids its Windows console-signalling restart path without masking intentional stops through automatic restarts.

**15 launcher/entry-point checks passed**, including actual launches from another working directory in PowerShell 7 and Windows PowerShell 5. Each used a test-owned workspace and port, served repeated requests for 12 seconds after readiness with one server process, rejected an occupied-port launch, and shut down only when explicitly signalled. **30 affected browser checks are green across the initial and corrected-file runs**: 15 analysis/UI checks passed initially, and all 15 motion/walkthrough checks passed after correcting a fixture that reset the saved preference on reload and waiting for animated mobile drawer bounds to settle. Exact viewport limits and persistence assertions remain unchanged. Ruff, frontend lint, TypeScript, **7 protocol tests** and the production build passed; the existing chunk-size advisory remains. No training, reserved scoring, paid AI, saved-data edits, commit or deployment occurred.

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

The recorded `evidence/bundle.json` is checked against the exact SHA-256 stored
in `evidence/replays-v1.5.json`. Its original bytes are deliberately marked
`-text` in `.gitattributes`: Git must not normalize line endings on Windows,
Linux or in source ZIPs. `tests/test_evidence_checkout.py` checks both Git
line-ending modes, archive output, checkout output and checksum rejection.
Changing that attribute without preserving the bytes can make verified replay
examples disappear while ordinary metrics continue to work.

GitHub Actions retains failed browser traces and the HTML report for seven
days under the `browser-failure-diagnostics` artifact. Download that artifact
from the failed run and use `npx playwright show-trace <trace.zip>` in
`frontend` to inspect the failure; local diagnostics remain ignored by Git
and excluded from Docker builds.

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

## Local workspace AI permission verification

The automatic generation behavior verified on 10 October was retired on 11 October. The permission persistence and revocation checks still apply; public routine actions now remain local regardless of permission. See the current checks below.

The 10 October permission update uses one explicit server-persisted approval for all local analysis contexts. Legacy scoped approvals are not silently promoted. Hosted demo and replay retain their existing restrictions, and saved analysis ownership remains unchanged. Turning permission off atomically clears cloud/unknown output and cancels active jobs while preserving evidence-only drafts; reapproval cannot resurrect revoked output.

Verification uses mocked provider responses and isolated browser workspaces, with no paid AI, training or reserved-validation requests. The focused assistant API/workspace suite passed 55 tests. The 38 relevant browser checks cover permission persistence, failures, one-time upgrade and reuse, cross-window revocation, analysis recovery, animations, both themes and 390 px layout. Restart persistence and all-owner revocation are covered at the SQLite/service boundary, including historical contracts and late writes. Dialog screenshots are saved locally under ignored `output/playwright/workspace-ai-*.png`.

Repeat the focused checks from the repository root:

```powershell
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
.venv\Scripts\python.exe -m pytest tests/test_workspace_ai_consent.py tests/test_assistant_api.py -q
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm test -- tests/workspace-ai-permission.spec.ts tests/analysis-recovery.spec.ts tests/investigation.spec.ts tests/ui-regressions.spec.ts tests/motion-preference.spec.ts --reporter=line
```

## Routine local analysis verification

The 11 October cleanup enforces zero provider admission on every routine action: result analysis, comparison, replay explanation, CSV review and brief creation/conversion. A key, presenter unlock, workspace permission or retry cannot enable paid generation through those routine tasks. The subsequent deep-investigation update below adds an explicit `deep` action; the earlier cleanup did not include it.

Verification passed 268 offline backend tests (one native Windows symlink permission skip and three integration tests deselected), including 17 new routine boundary cases. Those cases cover all model actions in full/demo/replay, actual synthetic CSV registration without training, unchanged mapping/dataset records, denied request fields, permission toggling, saved cloud reuse/brief/export/revocation and separation from an active mocked legacy job. Existing legacy-provider safeguards are exercised explicitly internally rather than treating public generation as supported.

The 39 relevant browser checks passed with fixture records, including saved AI labels, access recovery using GET only, absent AI setup in ordinary panels, brief reuse, failure recovery, keyboard/settings behavior, both themes, 390 px layout and animations. Ruff, lint, TypeScript, exact generated-type comparison, seven protocol tests and the production build passed. Twelve offline explanation cases retained essential facts, concrete checks and scope with zero provider requests. Existing bundle-size/dependency deprecation advisories remain. No paid provider requests, training or reserved-validation jobs were launched.

```powershell
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
$env:SIDEKICK_ASSISTANT_LIVE_EVAL = '0'
.venv\Scripts\python.exe -m pytest tests/test_routine_analysis.py tests/test_assistant_api.py tests/test_workspace_ai_consent.py tests/test_assistant_data.py -q
.venv\Scripts\python.exe scripts/evaluate_assistant.py --output output/routine-analysis-offline-evaluation.json
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm test -- tests/workspace-ai-permission.spec.ts tests/analysis-recovery.spec.ts tests/investigation.spec.ts tests/ui-regressions.spec.ts tests/motion-preference.spec.ts --reporter=line
```

The legacy evaluation script's explicit live switches still send paid provider requests and require separate authorization. Its output identifies the evaluated engine; successful legacy selection is not proof of the new deep report's usefulness. Saved schemas, IDs, evidence, ownership and provenance were preserved, with no migration or data deletion.

## Deep investigation verification

The explicit local-workspace `deep` task uses server-computed fault patterns followed by one structured model request. Mocked-provider tests cover consent admission, replay restrictions, aliased inputs, quantitative/URL/approval rejection, tentative explanations, conditional next tests, cited observations, missing coverage, comparisons, active-job reuse with brief switching, server restart, key removal, historical currency, editing, export and revocation. Ordinary tasks remain evidence-only. The frontend uses fixture reports for permission failures, loading, close/reopen without incidental cancellation, references, brief conversion, theme and mobile layout checks.

```powershell
$env:SIDEKICK_ASSISTANT_LIVE_ENABLED = '0'
$env:SIDEKICK_ASSISTANT_LIVE_EVAL = '0'
.venv\Scripts\python.exe -m pytest tests/test_deep_investigation.py tests/test_routine_analysis.py -q
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm test -- tests/deep-investigation.spec.ts tests/analysis-recovery.spec.ts tests/investigation.spec.ts tests/workspace-ai-permission.spec.ts --reporter=line
```

Run browser checks after the production build completes, and do not replace built assets while the fixture server is serving a suite. These offline checks establish contract and lifecycle behavior, not actual model usefulness or improved engineer decisions. No paid provider evaluation belongs in normal CI.

11 October closeout: 284 backend tests passed (one Windows symlink permission skip, three integration tests excluded), including 16 deep cases and the long-brief size boundary; generated types, Ruff, frontend lint/types, seven protocol cases, production build and twelve offline routine cases passed. The broad browser run passed 40 of 45 cases. Four new route-fixture failures were fixed, and the animation fixture now prepares its real response before releasing the animation gate. The fresh nine-case deep/motion rerun passed, verifying all 45 relevant cases across runs. A concurrent fixture-startup attempt timed out; the final ordinary configuration started successfully after the backend checks finished. Application animations were unchanged. No paid AI, training, reserved scoring, commit or deployment occurred.

## Analysis and brief presentation repair (11 October 2026)

The review editor fills its card and uses the current themed surface. Completed traces omit elapsed time because the record update timestamp also changes on saves, conversion and permission updates. Genuine revoked AI output has a neutral notice; unrelated request and save errors still show inline alerts. Only a permitted deep investigation offers a retry from that notice.

Revocation leaves completed, proven evidence-only results and drafts unchanged. Startup repairs the old false consent notice only for compatible completed local records with proven local draft provenance and no revocation tombstone. Cloud and unknown origins, real tombstones, recorded results, identifiers and timestamps remain intact.

Focused verification uses fixture records and no live provider requests:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_workspace_ai_consent.py tests/test_assistant_api.py tests/test_deep_investigation.py tests/test_routine_analysis.py -q --tb=short
npm --prefix frontend run build
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
npm --prefix frontend run test -- analysis-presentation.spec.ts analysis-recovery.spec.ts deep-investigation.spec.ts workspace-ai-permission.spec.ts investigation.spec.ts
```

Build before browser checks and leave the built files unchanged while the fixture server is running. Presentation coverage includes full editor width, themed background, keyboard focus and no horizontal overflow at 390 and 1280 pixels in both themes. Lifecycle suites cover permission checks, saved IDs, draft revision races and explicit retries. Session results are recorded in `output/analysis-presentation-verification.json`.

## Deep investigation verification repair (11 October 2026)

Offline regression fixtures reproduce alias-prefix rejection (`channel-10` versus `channel-1`), capitalization differences, and rejection of legitimate diagnostic checks. Verification now masks and resolves only complete known aliases, consistently ignores alias casing, and distinguishes a diagnostic check from an asserted diagnosis. Unknown references, invented numbers, unsupported conclusions and invalid citations remain rejected. Provider validation failures return fixed safe explanations without saving or exposing provider prose. Fallback traces say **Recorded evidence ready** rather than implying that an AI report completed.

The screenshot's original rejected provider output was not retained, so these reproduced defects cannot establish which rule rejected that particular response. No live requests or automatic retries were used to investigate or verify the repair. Actual provider quality remains unmeasured.

The focused backend command above covers the repair and access/lifecycle boundaries. Browser verification runs `npm --prefix frontend run test -- deep-investigation.spec.ts analysis-presentation.spec.ts` after the production build, with offline route fixtures. Session results are recorded in `output/deep-verification-fix-verification.json`.

## Deep test outcome contract repair (11 October 2026)

The subsequent failure identified the conditional-outcome verifier. Its prose keyword check could reject useful outcome explanations that omitted its small list of recognized words. The `sidekick-deep-v3` provider-only contract now requires separate `if_signal_observed` and `if_signal_absent` explanations. The server supplies explicit conditional framing and stores the existing `interpretation` field, preserving saved reports, review briefs, exports and generated public types. No migration or model change is needed. This follows the SDK's [structured-output schema guidance](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

Offline coverage includes both the recorded recommended augmented model and a logistic model, useful wording without the old keywords, required outcome fields, whitespace and duplicate rejection, unsupported causal conclusions, and the stored-text length boundary. Existing citation, numerical-claim, alias, privacy, consent, restart and brief checks remain in force. Exactly one mocked request is admitted; no provider retry was added. The original rejected prose was not retained, and actual provider success and usefulness are not established by these fixtures. Session results are recorded in `output/deep-outcomes-fix-verification.json`.

## Deep citation contract repair (11 October 2026)

The next screenshot identified a citation rejection. The previous provider schema allowed arbitrary strings for `observation_ids`; the prompt alone asked the model to choose inspected patterns. `sidekick-deep-v4` now builds a request-scoped response schema whose allowed citation values are exactly the observation IDs in the bounded evidence packet. Both hypotheses and proposed tests use those choices. The stored/public report shape remains unchanged. Repeated valid citations are deduplicated in their original order before verification; invented or out-of-scope IDs remain rejected, with a safe citation error and no automatic retry. Citations establish relevance to inspected observations, not the truth of a hypothesis.

Regression coverage inspects the SDK's strict schema for single and multiple observation sets, checks request isolation, accepts repeated valid citations, and rejects unknown references in both report sections. An additional test uses the installed `AsyncOpenAI` SDK with an HTTP mock transport to serialize the actual Responses request and parse a recommended augmented-model report. It checks the sent citation choices, one request, `store=false`, and the existing conditional-outcome conversion. This goes beyond replacing the provider client with a fake parser. The transport uses only a fixture key and cannot reach the provider.

Run the focused backend command in the presentation-repair section plus Ruff and generated-type consistency. The frontend and stored report schemas did not change in this repair, so the prior production build and eleven presentation/deep browser checks remain applicable; they are not newly claimed live-provider evidence. The original rejected prose was not retained, and these offline checks do not establish live success or engineer usefulness. Session results are recorded in `output/deep-citations-fix-verification.json`.

## Live deep-investigation repair (11 October 2026)

The user authorized at most five paid diagnostic requests. All five were recorded before admission, with SDK retries disabled, the existing model snapshot and `store=false`. They cost an estimated **$0.0123196** using the model's published input/output token prices, before any caching discount. The hard request limit was not exceeded; subsequent checks replayed captured responses without constructing a provider client.

Actual responses exposed brittle wording checks: legitimate uncertainty about deployment was treated as approval, and a procedure describing missing readings caused by simulated dropout was treated as a physical diagnosis. The tentative-explanation check also depended on particular words. `sidekick-deep-v7` supplies explicit hypothesis framing on the server, requires structured conditional outcomes and scoped citation choices, and reserves the summary/verdict for the server. It supplies recorded protocol boundaries, metric definitions and the actual warning-shortfall focus so the model does not confuse passing case limits with perfect detection or early-alarm burden with useful lead. Only the known missing-readings/dropout relationship is exempted from the causal wording check when dropout is present in the inspected evidence. Physical failure diagnoses, deployment approval, invented numbers/links and invalid references remain rejected.

The recommended **Augmented XGBoost · aug3** completed live in **5.31 seconds**, with no fallback, preserved evidence, saved-report reuse and review-brief conversion. The fifth response, for the failing **logistic regression · lr2**, exposed the remaining dropout false rejection. After that final narrow repair, both exact captured responses completed through the real API/save/reopen/brief pipeline without further paid requests. The latter is captured-response verification, not a sixth live request. Two pseudonymous qualitative provider responses are retained as offline regression fixtures; credentials and raw readings are excluded.

The fresh relevant backend gate passed **124 tests**. Ruff and exact generated-type comparison passed; stored/public types and database schema did not change. Playwright CLI displayed both captured real reports and their unchanged AI content in review briefs, checked visible expanded evidence, absence of errors and horizontal overflow at 1280 px dark and 390 px light. All assistant endpoints were intercepted during these four UI checks, admitting zero additional provider requests and making no changes to the user's saved jobs. The earlier frontend build remains applicable because this repair changes only backend behavior and tests.

Receipts and the five-request ledger are in ignored `output/deep-live-repair-20261011/`. Existing evidence and user data were preserved; no training, reserved scoring, commit or deployment occurred. Ordinary `tasks.ps1 api` does not reload backend source, so restart it to load this repair. Existing saved failures remain historical and do not automatically regenerate. These checks establish the repaired contract and observed provider success, not improved engineer decisions or a guarantee that every future provider response will pass verification.

## Deep report layout polish (11 October 2026)

Deep investigation now opens with the tentative explanation associated with the server's highest-priority test, followed by that visible recommended check. The alternative explanation remains visible. Conditional outcomes, other explanations/checks, uncertainty and full recorded patterns stay available through keyboard-accessible disclosures. Stored reports, briefs, exports, provider admission and hypothesis ordering on the server are unchanged.

Every deep disclosure uses the shared inset content wrapper, including recorded references, pattern lists and scope. The shared analysis-panel padding also covers ordinary evidence, limitations, analysis records and review supporting evidence. Pattern text no longer touches the panel edge. Long content wraps, conditional outcome line breaks remain readable, and the existing theme/motion controls are retained.

Fresh lint, TypeScript/production build and **15 browser tests** passed: deep report, analysis/brief presentation and motion-preference suites. New assertions check the visible first finding/check order, priority association without treating hypotheses as proven, collapsed supporting content, keyboard access and at least 16 px of left/right pattern inset at 390/1280 px in both themes. The initial desktop inset failures were corrected by increasing the shared padding, with no weaker assertion. Four additional intercepted UI checks used both captured provider reports; no new paid requests, training or scoring occurred. Build retained the existing large-chunk advisory. The design scan's existing neutral loading-shimmer warning is outside this refinement and was preserved intentionally. Receipt and screenshots: ignored `output/deep-ui-polish-20261011/`.

## Deep comparison repair (11 October 2026)

The user authorized four paid diagnostic requests for the aug3/lr2 comparison. Exactly four were admitted, with no provider retries and an estimated token cost of $0.0103096. The second request reproduced the screenshot's rejection: valid references such as `hypothesis 1` were mistaken for invented measurements. Verification now accepts only references to existing hypotheses in the same report. Unknown indices, decimal/percentage values, invented measurements, links and unsupported conclusions remain rejected.

The comparison evidence packet also previously selected all 24 patterns from lr2. Prompt v8 reserves space for both selected models, retaining failure-first ranking within the balanced subset and the existing input ceiling. Unused slots transfer to models with available patterns; no missing evidence is invented. Per-model supplied/available counts disclose the subset. Single-model ordering, stored/public schemas and recorded metrics remain unchanged.

The final two requests completed live in both selection orders (5.56 and 5.20 seconds), each with 12 recorded patterns per model, unchanged evidence, saved-report reopen and brief conversion. Their exact packets and qualitative responses are offline regression fixtures. The original rejected response has a separate validator-only fixture with its original citation scope; it is never reinterpreted against the new packet.

Fresh verification: **136 relevant backend tests passed**, Ruff passed across backend/app, tests and scripts, and generated types match exactly. Four Playwright CLI checks displayed captured real comparison reports and briefs at dark 1280 px and light 390 px, with no error or horizontal overflow. These checks intercepted every assistant route, admitted zero additional paid requests and changed no user records. Two browser fixture setup issues (missing compare capability and saved-record GET) were repaired before the successful rerun. Frontend source and built assets were unchanged by this backend repair.

Receipts, captures, screenshots and the hard four-request ledger are in ignored `output/deep-comparison-repair-20261011/`. No training, reserved scoring, migration, commit or deployment. Restart `tasks.ps1 api` to load the fix, then explicitly retry the failed comparison; saved failures do not regenerate automatically. Observed provider success does not establish causal truth or improved engineer decisions.

## Richer deep investigation inputs (11 October 2026)

Deep prompt v9 uses bounded supporting records: clean/faulted outcomes for an exactly matched model, history, partition, threshold and cycle axis; useful-window score margins, threshold crossings, streaks and warning transitions; recorded preprocessing methods; affected-channel quality; recorded fold outcomes; and matched clean-prediction contributions. History and fold identities use aliases. No raw reading arrays, feature reading values or serialized fitted models enter the provider packet. Examples are selected, repeated fault outcomes are not independent equipment, original profile statistics may include reserved records, and clean contributions do not explain faulted predictions or physical causes. Missing historical preprocessing/fold metadata is explicitly unavailable. New bundles capture those methods and already computed outcomes without launching execution or changing recorded scalar results.

Optional equipment type, sensor meaning and decision fields use existing Arc controls beside the deep action. They are deliberately sent, unverified context; automatic pilot/contact copying remains excluded. Empty fields preserve context identity; changed context has a separate identity. Supporting evidence can be cited and inspected under **Additional recorded inputs**. Supplemental facts participate in currency checks. Legacy saved reports reuse their existing IDs without paid regeneration, including conversion to a brief.

Fresh verification: **347 offline backend tests passed**, one skipped and three integration cases excluded. Fifteen new regression cases cover pairing mismatches, actual capture, fold partition scope, matched contributions, missing values, streak gaps, input bounds, context validation/identity, legacy reuse and one mocked provider request through brief conversion. Ruff, exact generated types, frontend lint, TypeScript/production build and all seven protocol tests passed. Browser checks covered 36 distinct deep/presentation/recovery/permission/motion cases: 35 first-run passes, then all seven deep cases passed after fixing a new test-only async request-capture race. Context inputs and supporting panels fit at 390/1280 px in light/dark themes; focus and saved IDs/request counts remain asserted. The mobile report screenshot was inspected. Existing deprecation/chunk advisories remain.

No paid requests, actual training jobs, reserved-validation jobs, data migrations, historical evidence edits, commits or deployment. The isolated browser server disabled live AI. Receipts are in ignored `output/deep-evidence-inputs-20261011/`; restart `tasks.ps1 api` to load the backend. Enriched evidence is available to new investigations. This verification establishes input correctness and lifecycle behavior; improved engineer decisions remain unmeasured.

## Final deep checks and polish (11 October 2026)

The minimal live check used exactly **two paid requests**, with SDK retries disabled and a hard two-request/$0.10 admission ledger. Estimated total cost was **$0.006958**. Both ran against the recorded aug3/lr2 comparison with sample engineer context in isolated temporary storage. The first v9 answer invented augmented input features and confirmed a hypothetical test outcome. The v10 verification call still contained unsupported superiority and raw-score comparison claims, plus numbered pattern references in prose. No third request was made.

Prompt/verification v11 distinguishes augmentation of training examples from added feature columns. It accepts only bounded prose references to the same item's exact cited patterns, while retaining the guards against measurements, unknown references, physical diagnoses and approval. Independently safe sections may be retained; unsafe sections are omitted and disclosed in report limitations. A partial report requires a safe hypothesis, a relevant safe next check and evidence gaps. Otherwise the recorded-evidence fallback remains. Missing historical records can explain why a mechanism cannot be confirmed; that is not affirmative proof. Cross-model raw score ordering is not accepted as a mechanism check.

The exact second provider response passed the repaired API, saved reuse, service restart, brief conversion, explicit draft save and HTML/JSON export pipeline **offline**, retaining one persistence/input-handling explanation and one useful next check. Missing-reading flags, median imputation and late/missed warnings remain in that check; both historical evidence gaps remain visible. This is captured-response verification, not a fresh paid generation under the final repair. The two-call sample does not establish an overall provider success rate or improved engineer decisions.

Supporting details now show readable percentages, yes/no values, method labels and compact decimals; full precision stays in the source records and provider packet. Two batched Playwright CLI visual rounds inspected actual captured context/report/support/brief content at dark 1440/390 px and light 390/1024 px. All assistant endpoints were intercepted, with no browser errors or horizontal overflow and zero additional paid calls. The important finding and next check remain first.

Fresh gate: **357 backend tests passed**, one optional test skipped and three training integration tests deselected. Ruff, exact generated types, frontend lint, TypeScript/production build, all seven protocol tests and **36 affected browser tests** passed. Existing deprecation and bundle-size advisories remain. The evidence bundle hash is unchanged. Receipts, ledger, captures and screenshots are in ignored `output/deep-final-check-20261011/`. No user consent/data changes, training, reserved scoring, subagents, commit or deployment. Restart `tasks.ps1 api` to load the repair; previously saved failures do not automatically regenerate.

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
# Deep diagnostic contract and semantic evaluation (11 October 2026)

`tests/test_deep_checks.py` covers model capabilities, request-scoped typed checks, observable/conditional pairing, invalid cross-model experiments, unavailable evidence, partial question-only output, and immutable paid captures. The existing deep/API/privacy suites cover saved identity, historical currency, consent, revocation, restart, brief conversion and export. Frontend deep tests check explicit evidence prerequisites and question-only presentation at 390/1280 px in both themes.

Run `.venv/Scripts/python.exe -m pytest tests -m "not integration" -q`, Ruff, generated-type consistency, frontend lint/build/protocol tests and the deep/presentation/recovery browser suites. Browser tests use intercepted fixtures; live AI evaluation stays outside CI.

Four explicitly authorized provider requests cost an estimated $0.015192. Structural acceptance concealed content defects in earlier attempts; those were scored as failures. Final processing verified the exact last capture offline, retaining one scoped question and no generated explanation. Detailed limitations and the actual method are recorded in [the diagnostic-contract evaluation](docs/arc/audits/2026-10-11-deep-check-contract-evaluation.md). This is not proof of engineer benefit or fresh generation after final postprocessing.

## Shared context and refined reasoning (11 October 2026)

`tests/test_experiment_context.py` checks separate metadata, restart/clearing, origin and mode boundaries, unknown records, immutable request snapshots, empty-focus identity compatibility and no AI admission on edits. Context is seeded with the pretraining request without entering the recorded experiment payload. The optional Pilot brief and later investigation setup share bounded equipment/decision capacities; only explicit context fields reach AI.

The affected browser gate includes `experiment-context.spec.ts`: the experiment POST is intercepted before job creation, so the tests inspect entered context and failure recovery without training. Deep setup covers saved context, failed saves, focus, reopen/request counts and abstention at 390/1280 px in both themes. The mechanical design detector returned no findings; rendered screenshots are also inspected.

Two additional paid requests cost an estimated **$0.0065304**, with no retries. The first exposed unqualified score assertions following a tentative opening. Current processing removes that explanation. The final paid answer retained one tentative mechanism, a competing alternative and a scoped diagnostic; exact-capture offline reuse/restart/brief/export checks pass. [Content review and limits](docs/arc/audits/2026-10-11-context-ai-refinement-evaluation.md). This still does not demonstrate consistent usefulness or better engineer decisions.


## Matched traces and deep added value

Run `.venv/Scripts/python.exe -m pytest tests/test_warning_traces.py tests/test_deep_checks.py tests/test_deep_evaluation.py -q` for paired excerpt/persistence semantics, scope, warning-state wording, exact captured answers, paid admission ceilings and honest benefit reporting. `npm --prefix frontend run test -- deep-investigation.spec.ts` covers recorded facts versus hypotheses/prerequisites in both themes at 390/1280 px. Fixtures never admit paid requests or start jobs.

`.venv/Scripts/python.exe scripts/evaluate_deep.py --output output/deep-review-new` is offline by default and prepares regular-analysis baselines, exact historical/fresh capture reviews, A/B HTML, a blank score sheet and facilitator key. Output directories must be new to preserve reviewer annotations. Two paid checks were authorized for this implementation; their durable `output/matched-traces-20261011/paid-ledger.json` is exhausted. Do not reset it to repeat calls. See [actual results and limitations](docs/arc/audits/2026-10-11-matched-traces-added-value.md). Generation latency is measured; engineer decision time and benefit remain unmeasured.
