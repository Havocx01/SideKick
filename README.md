# Sidekick

Sidekick trains equipment failure-warning models and tests whether their warnings
hold up when sensor readings go missing, freeze or drift. It compares models
against your chosen detection and early-alarm limits, with evidence for each result.

Built for ABB Accelerator 2026 by Adam Qablawi and Kareem Massoud.

[Watch the demo](https://github.com/user-attachments/assets/05654cc4-471e-45aa-9fc5-204009166601)

[Try the prototype](https://sidekick-e9lu.onrender.com/)

[Earlier benchmark walkthrough](https://github.com/user-attachments/assets/05654cc4-471e-45aa-9fc5-204009166601)

## Features

- Explore the recorded NASA C-MAPSS benchmark.
- Train models on a synthetic sample, or upload a CSV locally.
- Compare ordinary and fault-augmented training.
- Replay warnings and inspect the Evidence guide.
- Export results as an HTML report, JSON evidence and CSV metrics.

No API key is needed. A qualifying result supports further evaluation, not
automatic deployment or certification.

## Run locally

Install Python 3.11+ and Node.js 20+, then open a terminal in this folder.

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

Open [localhost:8000](http://127.0.0.1:8000) and choose **Run sample experiment**.
After initial setup, use the last two PowerShell commands or the last Bash command
to start again. Press Ctrl+C to stop.

## Hosted demo

The default Docker image runs a compact, real experiment designed for free hosting:

```bash
docker build -t sidekick .
docker run --rm -p 8000:8000 sidekick
```

Hosted samples use 30 short synthetic histories, three sensors and four model
configurations. Ten histories are evaluated across five folds; twenty remain
unscored. The local sample uses 60 histories and ten configurations. Neither sample
is field validation on ABB equipment.

The hosted demo allows two runs per browser per hour, with one active run across
the server and shared limits of six runs per hour and 24 per day. CSV uploads stay
local. Results require the same browser cookies and expire after 24 hours; server
restarts or idle shutdowns may clear them sooner. Export results to keep them.

For recorded results only, set `SIDEKICK_MODE=replay`. For local uploads and the
larger sample, use `full`. Local work is saved in `artifacts/workspace/`; the NASA
benchmark and historical evidence remain separate in `evidence/`.

[Reviewer walkthrough and submission checks](SUBMISSION.md)

Run `.\tasks.ps1 help` or `make help` for other commands.
