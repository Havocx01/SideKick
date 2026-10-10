# Sidekick V2

Sidekick tests whether equipment failure warnings survive missing, frozen or drifting sensors. Train models, inspect their weakest cases, and export the evidence.

Built for ABB Accelerator 2026, Theme 1, by Adam Qablawi and Kareem Massoud.

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

No API key is needed for these workflows. Optional AI investigates the selected evidence. This is a validation workbench, not a deployment approval system or live monitor.

## Try Sidekick

**No installation:** open the [public demo](https://sidekick-e9lu.onrender.com/) and choose **View walkthrough**. You can explore recorded results and train a sample. Uploads and full validation are available locally.

**Run on Windows:**

1. Download the [GitHub ZIP](https://github.com/Havocx01/SideKick/archive/refs/heads/main.zip) and **extract it**.
2. Open the extracted folder and double-click **Start Sidekick.cmd**.
3. Sidekick prepares itself and opens your browser. Start with **View walkthrough** or **Set up sample**.

The first launch needs internet and may take a few minutes. Install [Python](https://www.python.org/downloads/windows/) 3.11+ and [Node.js LTS](https://nodejs.org/en/download) once if the launcher asks for them. Python 3.12 was used for the Windows verification; Node.js must be 22.12+ or 20.19+.

For later launches, double-click **Start Sidekick.cmd** again. It reuses the installation and rebuilds the interface when files change. Keep its window open while using the app; press **Ctrl+C** to stop it. The local address is [http://127.0.0.1:8140](http://127.0.0.1:8140). No API key is needed.

If that address is already serving the same interface, the launcher opens it. If another app or an older Sidekick is using the port, it asks you to close that server first.

On macOS or Linux, with Python 3.11+ and Node.js installed, run `python3 scripts/launch.py` from the extracted folder. It performs the same setup and opens the app.

### Development commands

The existing `.\tasks.ps1` and `make` tasks remain available for setup, builds and frontend development. Run `.\tasks.ps1 web` or `make web` for frontend hot reload. The built app needs only the API server.

The launcher and Windows API command load `.env` from the repository folder if it exists. Restart the server after changing it. PowerShell environment variables override `.env`; clear an old key with `Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue` before starting.

With Docker Desktop running, `docker compose up --build` starts the local development API and web app. Open [localhost:5173](http://localhost:5173). Both published ports bind to host loopback; the processes still listen on their container interfaces so the web service can reach the API. Full mode is a local workspace. Sharing it remotely needs a separately designed authentication and access boundary.

Check the rendered bindings with `node scripts/check_local_docker.mjs`. This checks configuration without starting services or printing environment secrets.

### Keep saved experiments safe

Stop the local server, then run `.\tasks.ps1 backup` to save uploads, results, folders, analyses, briefs and validation history. GitHub contains the code, not this local data. Restore a trusted ZIP into a new workspace with `.\tasks.ps1 restore -Archive '<backup.zip>' -Destination '<new directory>'`; existing workspaces are never overwritten. See [backup and recovery](docs/workspace-backup.md) for startup settings, ownership and snapshot limitations.

Run `.\tasks.ps1 evaluation-pack` to prepare offline engineer review cases, a separate answer key and blank scoring sheets. See [engineer evaluation pack](docs/engineer-evaluation-pack.md). Creating the pack runs no training or paid AI.

## Try it

Start with **Start guided walkthrough**. It uses recorded NASA results to explain what Sidekick tests and how to read the warnings. It does not train models or score reserved histories.

To run something new, choose **Set up sample**, generate the data, review the split and protocol, then select **Train and challenge models**. The result bars show warnings in time, late and missed. Investigate a result, select two candidates to compare, or explain a warning in replay. Analysis follows the selected model and evaluation partition. Prepare a review brief when ready; edits stay separate from the original evidence.

Local runs reserve 20 histories. If a model qualifies, **Freeze recommendation** locks its fitted artifact, threshold, protocol and source identifiers. Reserved scoring requires an explicit confirmation and runs once. Histories already used in development or validation are blocked. The exposure ledger persists across server restarts; deleting the workspace destroys that audit history.

For an engineering pilot, open **Equipment pilot** from a completed local experiment. Name one equipment family and reviewer, record the decision and success measure, then confirm the data and test settings before reserved scoring. Freeze and evaluate the model, record the engineer's next action, and download the pilot evidence. Agreements and reviews are saved once per experiment. Optional review times and changed decisions are self-reported, not proven savings. A synthetic pilot only demonstrates this workflow; field usefulness still needs representative equipment data and an engineer's assessment.

[First equipment pilot checklist](PILOT.md)

The local sample uses 60 simulated histories and ten configurations. The hosted sample uses 30 shorter histories, three sensors and four configurations. Custom protocols, CSV uploads, freezing and final validation are local only. Hosted results expire; export them promptly.

CSVs need at least 25 distinct complete equipment histories, consecutive integer operating cycles, numeric sensors and failure information. An initial cycle above 1 is fine; missing cycle rows and copied histories are rejected. Development folds must contain enough scorable readings and both warning-label classes. Confirm histories reach failure if no failure-cycle column exists. Censored histories and timestamps are unsupported. If an embedded browser does not open the picker, use **Paste CSV instead** or Chrome/Edge.

## Optional AI

Set `OPENAI_API_KEY` in the server environment before starting Sidekick. The default model is `gpt-4.1-mini-2025-04-14`; override it with `SIDEKICK_ASSISTANT_MODEL`. Never put a key in frontend code or commit it.

AI uses read-only tools to inspect recorded model metrics, fault cases and warning events. It chooses evidence-backed assessments and a next check. Every displayed claim, number and link comes from Sidekick's verified evidence; the model cannot change results, launch training or approve deployment. Without live AI, the same tools follow a fixed investigation sequence.

Use **Review data** during CSV setup to check the current mapping and blockers. **Use draft mapping** edits column roles only; failure confirmation and training remain your actions. In an investigation, **Add to review brief** reuses the same evidence for an editable, exportable draft.

Completed analyses and review drafts are saved on the server. Reopening them or switching between analysis and a brief reuses the result for the same model and evidence. Draft edits save automatically; **Rerun with AI** starts a fresh request. Changing data, model, mapping or evaluation context uses separate results.

Closing an analysis leaves its saved job available. Temporary status failures retry automatically; **Refresh status** reads the existing job and does not start another AI request. Cached results track the configured live model and actual prompt/tool contracts. Human-edited briefs remain attached to the same scoped evidence across those upgrades.

Uploaded datasets and experiments each require explicit, revocable cloud consent. Only derived checks, column types, missing-value fractions, pseudonymous aliases and recorded metrics leave the server. Raw rows, column names, equipment IDs and file paths are excluded. `store=False` does not remove the provider's possible abuse-monitoring retention.

On a hosted demo, set `SIDEKICK_ASSISTANT_PRESENTER_CODE` as a server secret to enable private presenter access. Public visitors receive evidence-only analysis. Sidekick has no session, daily or hourly analysis allowance. Live analysis runs one request at a time. Each investigation can use up to eight read-only tool calls and one final selection, with a 45-second timeout. Replay mode never calls the provider. Set `SIDEKICK_ASSISTANT_LIVE_ENABLED=0` to disable cloud calls everywhere. `SIDEKICK_ASSISTANT_TASKS` (default `investigate,compare,warning,brief,data`) controls the workflows.

Public-demo storage has aggregate safety limits: `SIDEKICK_DEMO_ANALYSIS_MAX_RECORDS=2000`, `SIDEKICK_DEMO_ANALYSIS_MAX_BYTES=33554432` (32 MiB of reserved payload), `SIDEKICK_DEMO_FOLDER_MAX_RECORDS=2000`, and `SIDEKICK_DEMO_FOLDER_MAX_PER_VISITOR=100`. Each admitted analysis reserves room for its bounded result and a 12,000-character edited brief, including worst-case JSON escaping. These are storage limits, not request allowances; the byte budget can fill before the record limit. Eligible demo state expires after 24 hours. Capacity errors reject new storage before provider work; existing results, edits, exports, cancellation and folder organization remain available. Unexpired records are never evicted to admit another visitor. Local workspace storage is exempt. Monitor physical SQLite and WAL sizes separately; the payload budget is not a filesystem-size guarantee, and no per-request VACUUM runs.

Routine tests use mocked provider responses. After changing the model or prompt, run the small live evaluation with `SIDEKICK_ASSISTANT_LIVE_EVAL=1` and a server-side key: `python scripts/evaluate_assistant.py`. It reports which cases passed verification and does not print the key.

## Evidence limits

The recorded benchmark is simulated NASA FD001 data. Logistic regression `lr2` warns 80/80 histories on clean readings but only 41/80 under its weakest required sensor dropout. Leading ordinary and augmented XGBoost both retain 79/80 in their weakest required case. This historical comparison does not isolate augmentation's effect.

V1.5 adds separately verified `lr2` replay traces without changing the original benchmark metrics. The older benchmark's tree models have only their originally stored examples. Historical FD001 histories remain exposed.

The default 70% detection, 10% alarm burden and 10-to-30-cycle warning window are demonstration settings. Faults are simulated and not calibrated to ABB field measurements. Development results also select thresholds and configurations. Bootstrap intervals are exploratory. Fresh reserved results still do not establish performance on real ABB equipment.

[Verification and remaining pilot work](TESTING.md)
