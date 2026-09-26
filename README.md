# Sidekick

Sidekick trains equipment failure-warning models, tests them against missing,
frozen and drifting sensor readings, and compares how well their warnings hold
up. Each experiment produces a recommendation with supporting evidence.

ABB Accelerator 2026, Theme 1. Built by Adam Qablawi and Kareem Massoud.

## Run locally

Install Python 3.11 or newer and Node.js 20 or newer, then open a terminal in this
folder.

Windows PowerShell:

```powershell
.\tasks.ps1 setup
.\tasks.ps1 build
$env:SIDEKICK_MODE = 'full'
.\tasks.ps1 api
```

macOS or Linux, with Make installed:

```bash
make setup
make build
SIDEKICK_MODE=full make api
```

Open http://127.0.0.1:8000. After the first setup and build, only the last two
PowerShell commands, or the last Bash command, are needed. Press Ctrl+C in the
server terminal to stop the app. Rebuild after changing frontend code.

Installation needs internet access. Exploring the included benchmark and running
the sample experiment require no API key or dataset download. Optional settings
are listed in `.env.example`; set them in your shell or container environment.

## Features

- Explore the recorded NASA C-MAPSS evaluation.
- Generate 60 synthetic equipment histories and run a new local experiment.
- Upload a CSV up to 10 MB, preview it and confirm its column mapping.
- Set minimum detection and maximum early-alarm burden before training.
- Compare ordinary and fault-augmented models under a fixed set of sensor faults.
- Replay warnings for individual machines and inspect the evidence in the sidebar.
- Reopen saved experiments and export an HTML report, JSON evidence and CSV metrics.

Choose **Run sample experiment** on the home screen to try the complete workflow.
Check the data and equipment split, confirm the acceptance limits, then start
training. Results open when the experiment finishes.

For uploads, provide equipment IDs, integer cycle indices and numeric sensor
columns. Histories must reach failure. Supply a failure-cycle column or explicitly
confirm that the final reading marks failure. Incomplete histories are not
supported. The data check explains invalid mappings and insufficient equipment
before training starts. Failure targets must not also be selected as sensors.

One experiment can run at a time. The app shows its current stage and elapsed
time, supports cancellation and stops runs after 15 minutes. Refreshing the page
preserves progress; a server restart marks unfinished jobs as interrupted.

## Data and evidence

`artifacts/workspace/` holds uploaded data, experiment metadata, logs and results.
Each experiment has its own files. Browser experiments never overwrite the
recorded benchmark in `evidence/bundle.json`.

Keep `evidence/archive/` alongside the current bundle. Its historical JSON files
record which holdout engines were previously examined, and the evaluation script
uses them to prevent reuse as an independent validation set.

The initial 70% detection and 10% early-alarm burden limits are demonstration
settings. NASA data and injected faults are simulated. These results do not
establish performance on ABB equipment or authorize deployment. The browser
does not score the holdout.

The Evidence guide answers supported questions from the selected experiment's
metrics using fixed templates. It makes no external model calls. Evidence exports
include configuration, limitations and source identifiers; raw uploaded data and
raw sensor replay values are excluded.

## Replay and development

Set `SIDEKICK_MODE=replay` to serve recorded evidence with upload and training
disabled. The production Docker image uses this mode:

```bash
docker build -t sidekick .
docker run --rm -p 8000:8000 sidekick
```

For frontend development, run `.\tasks.ps1 api` and `.\tasks.ps1 web` in separate
terminals. The frontend opens on http://127.0.0.1:5173 and proxies requests to the
API on port 8000. `docker compose up --build` provides the same two services.

Run `.\tasks.ps1 help` or `make help` for the remaining commands. Supporting
scripts download NASA data, run the broader fault matrix, regenerate the
benchmark bundle, check reproducibility and perform a guarded holdout evaluation.
The pipeline and bundle commands replace the recorded benchmark when run.
