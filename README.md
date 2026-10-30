# Sidekick V2

Sidekick tests whether equipment failure warnings survive missing, frozen or drifting sensors. Train models, inspect their weakest cases, and export the evidence.

Built for ABB Accelerator 2026, Theme 1

The Nebius x NVIDIA adaptation adds fault investigations. NVIDIA Nemotron (`nvidia/nemotron-3-super-120b-a12b` on Nebius Token Factory) proposes compound sensor-fault experiments under saved call and token limits. Sidekick runs them against fixed development models, classifies the results with code, reduces failures to simpler cases and compares remedies. Use it from the **Investigations** workbench, the HTTP API or the CLI. See the [setup](docs/nebius-phase-1.md), [evaluation](docs/nebius-phase-2.md) and [investigation](docs/nebius-phase-3.md) guides and the [submission notes](docs/nebius-submission.md). Existing experiment protocols remain single-sensor.

Run the whole investigation on synthetic data with one command, with no API key: `.venv\Scripts\python.exe scripts/demo_investigation.py`.

[Public demo](https://sidekick-e9lu.onrender.com/) · [Reviewer walkthrough](SUBMISSION.md)

## Features

- Recorded NASA C-MAPSS benchmark, clearly separated from new runs.
- Five-step guided walkthrough explaining healthy readings, sensor faults and the evidence.
- Real local training on synthetic data or a CSV up to 10 MB.
- Explicit column mapping and complete failure-history checks.
- Configurable warning windows, acceptance limits and single-sensor fault scenarios.
- Logistic regression, ordinary and augmented XGBoost, and an age-only baseline.
- Detection, alarm burden, coverage and candidate-specific warning replays.
- Play/Pause and a cycle slider for synchronized playback of stored warning and sensor traces.
- Matched ordinary/augmented comparisons with exploratory paired bootstrap intervals.
- Data review, contextual investigations, model comparison and stored warning explanations.
- Editable review briefs with linked evidence and separate exports.
- Frozen local models and an explicit, one-time reserved-equipment evaluation.
- Equipment pilot agreements and an engineer decision tied to the frozen model's final results.
- HTML, JSON, CSV and provenance exports. Raw readings and model files are excluded.

No API key is needed for these workflows. Routine analysis explains the selected recorded evidence locally. This is a validation workbench, not a deployment approval system or live monitor.

## Try Sidekick

**No installation:** open the [public demo](https://sidekick-e9lu.onrender.com/) and choose **View walkthrough**. You can explore recorded results and train a sample. Uploads and full validation are available locally.

**Run on Windows:**

1. Download the [GitHub ZIP](https://github.com/Havocx01/SideKick/archive/refs/heads/main.zip) and **extract it**.
2. Open the extracted folder and double-click **Start Sidekick.cmd**.
3. Sidekick prepares itself and opens your browser. Start with **View walkthrough** or **Set up sample**.

The first launch needs internet and may take a few minutes. Install [Python](https://www.python.org/downloads/windows/) 3.11+ and [Node.js LTS](https://nodejs.org/en/download) once if the launcher asks for them. Python 3.11.9 was used for the Windows verification; Node.js must be 22.12+ or 20.19+.

For later launches, double-click **Start Sidekick.cmd** again. It reuses the installation and rebuilds the interface when files change. Keep its window open while using the app; press **Ctrl+C** to stop it. The local address is [http://127.0.0.1:8140](http://127.0.0.1:8140). No API key is needed.

If that address is already serving the same interface, the launcher opens it. If another app or an older Sidekick is using the port, it asks you to close that server first.

On macOS or Linux, with Python 3.11+ and Node.js installed, run `python3 scripts/launch.py` from the extracted folder. It performs the same setup and opens the app.

### Development commands

The existing `.\tasks.ps1` and `make` tasks remain available for setup, builds and frontend development. Run `.\tasks.ps1 web` or `make web` for frontend hot reload. The built app needs only the API server.

Start the built app with `.\tasks.ps1 api` or `make api`. Normal API launches do not use the development reloader. Use `.\tasks.ps1 api -Reload` or `make api-dev` only while editing backend code; these watch the backend directory. `.\tasks.ps1 api -Port 8000` uses a different local port. Keep the terminal open while using Sidekick.

Animations are on by default. The **Animations** switch beside the theme control saves your choice, including turning them off, across refreshes.

The launcher and Windows API command load `.env` from the repository folder if it exists. Restart the server after changing it. PowerShell environment variables override `.env`; clear an old key with `Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue` before starting.

With Docker Desktop running, `docker compose up --build` starts the local development API and web app. Open [localhost:5173](http://localhost:5173). Both published ports bind to host loopback; the processes still listen on their container interfaces so the web service can reach the API. Full mode is a local workspace. Sharing it remotely needs a separately designed authentication and access boundary.

Check the rendered bindings with `node scripts/check_local_docker.mjs`. This checks configuration without starting services or printing environment secrets.

### Keep saved experiments safe

Stop the local server, then run `.\tasks.ps1 backup` to save uploads, results, folders, analyses, briefs and validation history. GitHub contains the code, not this local data. Restore a trusted ZIP into a new workspace with `.\tasks.ps1 restore -Archive '<backup.zip>' -Destination '<new directory>'`; existing workspaces are never overwritten. See [backup and recovery](docs/workspace-backup.md) for startup settings, ownership and snapshot limitations.

Run `.\tasks.ps1 evaluation-pack` to prepare offline engineer review cases, a separate answer key and blank scoring sheets. See [engineer evaluation pack](docs/engineer-evaluation-pack.md). Creating the pack runs no training or paid AI.

## Try it

Start with **View walkthrough**. Its introductory disclosure uses recorded NASA results to explain what Sidekick tests and how to read the warnings. It does not train models or score reserved histories. For onsite judging, use the [presentation runbook and offline fallback checklist](docs/judging-guide.md).

To run something new, choose **Set up sample**, generate the data, review the split and protocol, then select **Train and challenge models**. The result bars show warnings in time, late and missed. Investigate a result, select two candidates to compare, or explain a warning in replay. Analysis follows the selected model and evaluation partition. Prepare a review brief when ready; edits stay separate from the original evidence.

Local runs reserve 20 histories. If a model qualifies, **Freeze recommendation** locks its fitted artifact, threshold, protocol and source identifiers. Reserved scoring requires an explicit confirmation and runs once. Histories already used in development or validation are blocked. The exposure ledger persists across server restarts; deleting the workspace destroys that audit history.

For an engineering pilot, open **Equipment pilot** from a completed local experiment. Name one equipment family and reviewer, record the decision and success measure, then confirm the data and test settings before reserved scoring. Freeze and evaluate the model, record the engineer's next action, and download the pilot evidence. Agreements and reviews are saved once per experiment. Optional review times and changed decisions are self-reported, not proven savings. A synthetic pilot only demonstrates this workflow; field usefulness still needs representative equipment data and an engineer's assessment.

[First equipment pilot checklist](PILOT.md)

The local sample uses 60 simulated histories and ten configurations. The hosted sample uses 30 shorter histories, three sensors and four configurations. Custom protocols, CSV uploads, freezing and final validation are local only. Hosted results expire; export them promptly.

CSVs need at least 25 distinct complete equipment histories, consecutive integer operating cycles, numeric sensors and failure information. An initial cycle above 1 is fine; missing cycle rows and copied histories are rejected. Development folds must contain enough scorable readings and both warning-label classes. Confirm histories reach failure if no failure-cycle column exists. Censored histories and timestamps are unsupported. If an embedded browser does not open the picker, use **Paste CSV instead** or Chrome/Edge.

## Analysis and saved AI output

**Analyze result**, **Compare selected**, **Explain warning**, **Review data** and **Prepare review brief** use local recorded-evidence analysis. These actions make no provider requests, even when a server key and AI permission are configured. Preparing a brief also reuses a permitted saved deep report for the same models and partition.

**Deep investigation** is a deliberate AI action on a completed model result in a local workspace. For two models, open **Compare selected**, then choose **Deep investigation**. It connects recorded fault patterns, proposes tentative explanations with alternatives, identifies evidence gaps, and prioritizes concrete next tests with expected signals and conditional outcomes. Citations lead to server-computed observations; they establish relevance, not causation. Numbers, limits, verdicts and links remain server-owned. No training or reserved validation is launched.

For Nebius, set `SIDEKICK_ASSISTANT_PROVIDER=nebius` and `NEBIUS_API_KEY` on the server; the default model is `nvidia/nemotron-3-super-120b-a12b`. Remove an old `SIDEKICK_ASSISTANT_MODEL` override or set it explicitly to a model available on your endpoint. Keep `SIDEKICK_ASSISTANT_LIVE_ENABLED=1`, restart Sidekick, and enable workspace permission through **AI settings** or the deep-investigation prompt. A new Nebius endpoint needs its own approval; existing OpenAI approval does not transfer. See [configuration and the bounded connectivity check](docs/nebius-phase-1.md).

Existing OpenAI setups remain supported with `SIDEKICK_ASSISTANT_PROVIDER=openai` (the compatibility default), `OPENAI_API_KEY`, and the default `gpt-4.1-mini-2025-04-14` model. Each new deep context uses one structured provider request with no automatic provider retries. Reopening uses the saved report, including after a server restart; provider, model or prompt changes label historical output rather than automatically regenerating it. Permission alone never starts a request. If you explicitly restrict `SIDEKICK_ASSISTANT_TASKS`, include `deep` to enable this action. Hosted demo and replay remain evidence-only for new work.

The server inspects all recorded required fault rows in the chosen partition and supplies at most 24 prioritized model/channel/type/duration patterns, including timing and severity ranges. Larger sets explicitly disclose omitted patterns. Aggregate patterns are descriptive, not independent samples or controlled causal comparisons. Missing values and unknown coverage remain explicit. A failed, interrupted or unavailable investigation offers recovery where permitted; verification failures show local evidence and do not retry automatically.

Deep input also includes bounded, recorded diagnostic summaries when available: matched clean/faulted warnings on the same history, each model's selected threshold and score margins, preprocessing methods, sensor quality, fold outcomes and matched clean-prediction contributions. Raw traces, sensor readings and equipment IDs stay local. New experiment evidence records actual preprocessing and fold outcomes; older runs explicitly report unavailable metadata instead of assuming today's implementation. The optional **Pilot brief** before training saves equipment type, sensor meaning and the supported decision as shared experiment context. These descriptions do not affect training or scoring. **Deep investigation** opens a setup panel with an optional focused question and collapsed **Experiment context** for later edits. Context saves locally; only **Start investigation** admits AI work. Explicit shared descriptions are sent as unverified context; other pilot notes and contacts are excluded. Saved investigations retain their original context snapshot. Supporting records are accessible under **Additional recorded inputs** in the saved report.

Completed analyses and review drafts are saved on the server. Reopening or switching between analysis and a brief reuses the saved result for the same model and evidence; draft edits save automatically. **Add to review brief** converts the current answer into an editable draft without another investigation. Changing data, mapping or evaluation context uses separate results. Regular analysis retains its concise, verified claims, numeric references and next checks.

Use **Review data** during CSV setup to check the current mapping and blockers. **Use draft mapping** edits column roles only; failure confirmation and training remain your actions. Closing an analysis preserves its saved record. **Refresh status** reads an existing record; **Retry analysis** can recover local failures without paid work.

Older saved AI answers and edited briefs remain readable under their existing ownership, evidence and permission checks. They are labelled **Previously saved AI analysis**. In the local app, **AI settings** beside the theme and animation controls manages the server-persisted workspace permission and access to those answers. Enabling permission does not launch AI. Turning it off cancels active AI work and removes cloud-derived or unknown-origin output while retaining proven evidence-only drafts and recorded test data. Historical hosted presenter access and replay restrictions remain enforced.

The retired claim-selection provider remains internal for regression/evaluation coverage. Only an explicit `deep` task admits new provider work through the app. Keep keys on the server and out of version control. Existing timeout, consent, cancellation, ownership, draft-saving and export safeguards apply to the new report.

Public-demo storage has aggregate safety limits: `SIDEKICK_DEMO_ANALYSIS_MAX_RECORDS=2000`, `SIDEKICK_DEMO_ANALYSIS_MAX_BYTES=33554432` (32 MiB of reserved payload), `SIDEKICK_DEMO_FOLDER_MAX_RECORDS=2000`, and `SIDEKICK_DEMO_FOLDER_MAX_PER_VISITOR=100`. Each admitted analysis reserves room for its bounded result and a 12,000-character edited brief, including worst-case JSON escaping. These are storage limits, not request allowances; the byte budget can fill before the record limit. Eligible demo state expires after 24 hours. Capacity errors reject new storage before provider work; existing results, edits, exports, cancellation and folder organization remain available. Unexpired records are never evicted to admit another visitor. Local workspace storage is exempt. Monitor physical SQLite and WAL sizes separately; the payload budget is not a filesystem-size guarantee, and no per-request VACUUM runs.

Routine tests prove zero provider calls on routine analysis paths. Deep-investigation tests use a mocked structured provider to check scope, privacy, citations, conditional tests, one-request behavior, fallback, reuse, restart and brief conversion. These checks do not establish the usefulness of actual model output for engineers. `python scripts/evaluate_assistant.py` still evaluates the offline legacy/local rubric; its explicit live switches target the retired engine and require separate authorization.

Deep investigations also receive short aligned excerpts of compatible stored clean/faulted development scores and active warnings, with their own threshold, persistence rules and explicit gaps. Raw sensor readings remain excluded. The inspector separates recorded facts from tentative explanations and missing evidence. Existing saved answers stay historical; no model/prompt update silently regenerates them. `python scripts/evaluate_deep.py --output output/deep-review-new` compares regular analysis with immutable captures offline and prepares an A/B engineer review pack. See [testing](TESTING.md) for verification commands and limitations.

## Evidence limits

The recorded benchmark is simulated NASA FD001 data. Logistic regression `lr2` warns 80/80 histories on clean readings but only 41/80 under its weakest required sensor dropout. Leading ordinary and augmented XGBoost both retain 79/80 in their weakest required case. This historical comparison does not isolate augmentation's effect.

V1.5 adds separately verified `lr2` replay traces without changing the original benchmark metrics. The older benchmark's tree models have only their originally stored examples. Historical FD001 histories remain exposed.

The default 70% detection, 10% alarm burden and 10-to-30-cycle warning window are demonstration settings. Faults are simulated and not calibrated to ABB field measurements. Development results also select thresholds and configurations. Bootstrap intervals are exploratory. Fresh reserved results still do not establish performance on real ABB equipment.

[Verification and remaining pilot work](TESTING.md)
