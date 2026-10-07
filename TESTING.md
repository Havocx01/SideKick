# Sidekick V2 verification

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
npm run build
npx playwright install chromium
npm test
```

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
