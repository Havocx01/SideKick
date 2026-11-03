# Sidekick

Sidekick tests whether equipment-warning models still warn in time when sensors go missing, freeze or drift. Its React interface and FastAPI backend support model preparation, reproducible experiments, failure reduction, remedy comparisons and evidence exports. Optional NVIDIA Nemotron requests through Nebius propose experiments; deterministic code measures the outcomes.

[Public demo](https://sidekick-e9lu.onrender.com/) · [MIT license](LICENSE)

## Run locally

Install Python 3.11+ and Node.js 22.12+ or 20.19+. Download or clone the repository, then double-click **Start Sidekick.cmd** on Windows. On macOS/Linux, run:

```sh
python3 scripts/launch.py
```

The launcher creates `.venv`, installs dependencies, builds the interface and opens http://127.0.0.1:8140. The first launch needs internet. Keep its terminal open; Ctrl+C stops the server. No API key is needed for recorded evidence or local training.

Open **Investigations**, choose **Prepare sample models**, and review their baseline performance. Create an investigation, choose a model and pooled or per-machine alarm limits, then run saved proposals. Results and budgets persist across refreshes and restarts. Threshold checks report development tradeoffs without applying changes.

For a complete synthetic demonstration without paid requests:

```powershell
.venv\Scripts\python.exe scripts/demo_investigation.py
```

On macOS/Linux, substitute `.venv/bin/python` for the Windows virtual-environment path. The example deliberately uses a fragile 0.95 threshold to demonstrate failure, replay, reduction, remedies and fresh-history assessment. It is not a recommended operating threshold.

## Optional AI

Copy [.env.example](.env.example) to `.env` and configure your own server-side credentials:

```dotenv
SIDEKICK_MODE=full
SIDEKICK_ASSISTANT_PROVIDER=nebius
SIDEKICK_ASSISTANT_MODEL=nvidia/nemotron-3-super-120b-a12b
SIDEKICK_ASSISTANT_LIVE_ENABLED=1
NEBIUS_API_KEY=
TAVILY_API_KEY=
```

Restart after changing settings. Shell environment variables override `.env`. Enable workspace AI permission and approve the specific action in the interface. Setting a key or opening saved results starts no inference. Tavily is optional and used only for requested fault research. The OpenAI SDK supplies compatible transport to Nebius; no OpenAI key is needed.

Nemotron receives the concern, aliased channels, reviewed descriptions, bounds and aggregate results. Research sends a query to Tavily and source excerpts to Nemotron. Review each transfer before approving. Saved call/token allowances and failures do not reset on restart. Each research action permits one search and one model request with a 5,120-token completion ceiling. Citations are suggestions, not measured fault evidence.

## Data and equipment evaluation

The CSV workflow accepts files up to 10 MiB with at least 25 complete run-to-failure histories. Use distinct equipment IDs, integer operating cycles, numeric sensors and documented failure cycles. If failure cycles are omitted, explicitly confirm that every history ends in failure. The minimum leaves little development data; it does not establish a strong study. Timestamps and censored histories require a supported adaptation.

Before a study, agree the equipment family, failure definition, warning windows, alarm limits, fault assumptions and decision with a qualified reviewer. Keep equipment-separated development and reserved histories. Freeze a procedure before assessing untouched histories once; an interrupted assessment still exposes them. Retuning requires different unseen histories. Record excluded records, unavailable alarm windows, reviewer observations and limitations. Missing windows are not zero alarms.

Recorded investigations are synthetic evidence tied to saved models and revisions. Their supplied faults and fragile thresholds do not establish field reliability, savings or an advantage over simpler search. The measured-bearing development study has no accepted remedy under its provisional per-machine limits. A synthetic 0.2 cutoff selected in development also failed a later 120-history check: worst-machine alarm burden reached 6.78%, above the 5% limit. No production threshold was changed.

Raw vibration experiments require verified, source-bound recordings. Partial-burst faults, raw remote execution, raw augmentation and fresh raw validation from feature CSVs alone are unsupported. Fitted contexts require matching source, dependencies and platform; prepare new contexts after source changes. Historical records remain readable.

## Development and tests

The repository keeps app source, launch/maintenance scripts, deployment files, required recorded evidence, tests and CI. Local datasets and saved work belong in ignored `data/` and `artifacts/`; generated reports belong in ignored `output/`. Never commit credentials or private equipment data.

Run `./tasks.ps1 help` for PowerShell tasks; Unix equivalents are in `Makefile`. `./tasks.ps1 web` starts frontend development and `./tasks.ps1 api` serves the built app. `docker compose up --build` starts local development services at http://localhost:5173.

Run backend checks from the root:

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/generate_types.py
git diff --exit-code frontend/src/api/types.ts
```

Then run frontend checks:

```powershell
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm run test:protocol
npm run build
npx playwright install chromium
npm test
```

On Unix, export `SIDEKICK_TEST_PYTHON` with the absolute `.venv/bin/python` path. Browser tests use isolated workspaces. Keep `SIDEKICK_ASSISTANT_LIVE_ENABLED=0` and `SIDEKICK_ASSISTANT_LIVE_EVAL=0` for routine tests, which mock paid services. CI also builds and checks worker/public-demo containers. Preserve `evidence/bundle.json` byte-for-byte; checksums establish integrity, not authenticity.

## Hosting

The default Docker image and `render.yaml` serve the restricted public demo. `Dockerfile` also provides `replay`, `demo` and private `hosted` targets. Container contexts/workers use Python 3.11.9 on Linux with [pinned dependencies](docker/runtime-constraints.txt). Native Windows fits may differ in the last bits.

For a private full workspace, use a Docker host, a domain pointing to it and ports 80/443. Configure access and start the prepared stack:

```powershell
.venv\Scripts\python.exe scripts/create_hosted_login.py --owner adam --origin https://workspace.example.com
node scripts/check_hosted_compose.mjs
docker compose --env-file .env.hosted -f compose.hosted.yaml up --build -d
```

Replace the example origin. The helper prompts for a password, writes its salted hash to `.env.hosted`, and sets paid allowances to zero. Keep that file private. Caddy supplies HTTPS; named volumes persist the workspace and certificates. Each deployment owns one workspace; changing owners requires separate storage. Preserve volumes on updates. Verify real HTTPS, sign-in/out, private-route denial, restart persistence and backup/restore before relying on a deployment. `/api/health` reports the deployed revision.

Paid actions additionally require explicit finite `SIDEKICK_HOSTED_MAX_CALLS`, `SIDEKICK_HOSTED_MAX_COMPLETION_TOKENS` and `SIDEKICK_HOSTED_MAX_SEARCHES` allowances. Reservations persist across failures and reset by UTC date; they are not billing guarantees. Per-action approval still applies. Sessions expire within eight hours; password changes invalidate sessions without deleting saved work.

## Backup and recovery

Stop the app and finish or cancel jobs before backing up:

```powershell
.\tasks.ps1 backup -OutputPath 'D:\Sidekick backups\workspace.zip'
.\tasks.ps1 verify-backup -Archive 'D:\Sidekick backups\workspace.zip'
.\tasks.ps1 restore -Archive 'D:\Sidekick backups\workspace.zip' -Destination 'D:\Sidekick recovered'
```

Backups preserve datasets, artifacts, SQLite records, exposure history and recorded evidence. They exclude app code, environment credentials and browser cookies. Archives contain private data and are not encrypted; store them securely on separate storage. Restore only trusted archives into a new directory. The original workspace is retained.

To use a restored workspace, set `SIDEKICK_DATA_DIR`, `SIDEKICK_ARTIFACTS_DIR` and `SIDEKICK_BUNDLE_PATH` to its `data`, `artifacts` and `evidence/bundle.json` paths, then start the API using compatible source and dependencies. Original ownership remains enforced; recovery does not transfer browser sessions or reset exposure history. Retain newer exposure records when recovering an older snapshot.

Sidekick began as an ABB Accelerator project and later added the Nemotron workbench. The project is MIT licensed; dataset and dependency terms apply separately.
