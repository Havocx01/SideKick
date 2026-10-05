# Sidekick v1.5

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
- Evidence guide scoped to the candidate and evaluation partition being inspected.
- Frozen local models and an explicit, one-time reserved-equipment evaluation.
- HTML, JSON, CSV and provenance exports. Raw readings and model files are excluded.

No API key is needed. This is a validation workbench, not a deployment approval system or live monitor.

## Run locally

Requires Python 3.11+ and Node.js 22.12+ (or 20.19+).

From the repository folder in PowerShell:

```powershell
.\tasks.ps1 setup
.\tasks.ps1 build
$env:SIDEKICK_MODE = 'full'
.\tasks.ps1 api
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Keep the terminal open. After setup, only the last two commands are needed. Press Ctrl+C to stop.

On macOS or Linux:

```bash
make setup
make build
SIDEKICK_MODE=full make api
```

For frontend development, run `.\tasks.ps1 web` or `make web` in another terminal. The built app needs only the API server.

## Try it

Start with **Start guided walkthrough**. It uses recorded NASA results to explain what Sidekick tests and how to read the warnings. It does not train models or score reserved histories.

To run something new, choose **Set up sample**, generate the data, review the split and protocol, then select **Train and challenge models**. The result bars show warnings in time, late and missed. Open **Sensor faults** to inspect a heatmap cell, or choose an Evidence guide question for an explanation. The summary follows the inspected model; the recommendation is labeled separately. Test settings and technical details expand when needed. Export the evidence when finished.

Local runs reserve 20 histories. If a model qualifies, **Freeze recommendation** locks its fitted artifact, threshold, protocol and source identifiers. Reserved scoring requires an explicit confirmation and runs once. Histories already used in development or validation are blocked. The exposure ledger persists across server restarts; deleting the workspace destroys that audit history.

The local sample uses 60 simulated histories and ten configurations. The hosted sample uses 30 shorter histories, three sensors and four configurations. Custom protocols, CSV uploads, freezing and final validation are local only. Hosted results expire; export them promptly.

CSVs need at least 25 complete equipment histories, integer cycle indices, numeric sensors and failure information. Confirm histories reach failure if no failure-cycle column exists. Censored histories and timestamps are unsupported. If an embedded browser does not open the picker, use **Paste CSV instead** or Chrome/Edge.

## Evidence limits

The recorded benchmark is simulated NASA FD001 data. Logistic regression `lr2` warns 80/80 histories on clean readings but only 41/80 under its weakest required sensor dropout. Leading ordinary and augmented XGBoost both retain 79/80 in their weakest required case. This historical comparison does not isolate augmentation's effect.

V1.5 adds separately verified `lr2` replay traces without changing the original benchmark metrics. The older benchmark's tree models have only their originally stored examples. Historical FD001 histories remain exposed.

The default 70% detection, 10% alarm burden and 10-to-30-cycle warning window are demonstration settings. Faults are simulated and not calibrated to ABB field measurements. Development results also select thresholds and configurations. Bootstrap intervals are exploratory. Fresh reserved results still do not establish performance on real ABB equipment.

[Verification and remaining pilot work](TESTING.md)
