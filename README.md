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
- Contextual result investigation, two-model comparison and warning explanations.
- Editable review briefs with linked evidence and separate exports.
- Frozen local models and an explicit, one-time reserved-equipment evaluation.
- Equipment pilot agreements and an engineer decision tied to the frozen model's final results.
- HTML, JSON, CSV and provenance exports. Raw readings and model files are excluded.

No API key is needed for these workflows. Optional AI prioritizes verified findings. This is a validation workbench, not a deployment approval system or live monitor.

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

To run something new, choose **Set up sample**, generate the data, review the split and protocol, then select **Train and challenge models**. The result bars show warnings in time, late and missed. Investigate a result, select two candidates to compare, or explain a warning in replay. Analysis follows the selected model and evaluation partition. Prepare a review brief when ready; edits stay separate from the original evidence.

Local runs reserve 20 histories. If a model qualifies, **Freeze recommendation** locks its fitted artifact, threshold, protocol and source identifiers. Reserved scoring requires an explicit confirmation and runs once. Histories already used in development or validation are blocked. The exposure ledger persists across server restarts; deleting the workspace destroys that audit history.

For an engineering pilot, open **Equipment pilot** from a completed local experiment. Name one equipment family and reviewer, record the decision and success measure, then confirm the data and test settings before reserved scoring. Freeze and evaluate the model, record the engineer's next action, and download the pilot evidence. Agreements and reviews are saved once per experiment. Optional review times and changed decisions are self-reported, not proven savings. A synthetic pilot only demonstrates this workflow; field usefulness still needs representative equipment data and an engineer's assessment.

[First equipment pilot checklist](PILOT.md)

The local sample uses 60 simulated histories and ten configurations. The hosted sample uses 30 shorter histories, three sensors and four configurations. Custom protocols, CSV uploads, freezing and final validation are local only. Hosted results expire; export them promptly.

CSVs need at least 25 complete equipment histories, integer cycle indices, numeric sensors and failure information. Confirm histories reach failure if no failure-cycle column exists. Censored histories and timestamps are unsupported. If an embedded browser does not open the picker, use **Paste CSV instead** or Chrome/Edge.

## Optional AI

Set `OPENAI_API_KEY` in the server environment before starting Sidekick. The default model is `gpt-4.1-mini-2025-04-14`; override it with `SIDEKICK_ASSISTANT_MODEL`. Never put a key in frontend code or commit it.

AI ranks recorded findings and suggested checks and adds a short interpretation, labelled as generated text. Sidekick rejects interpretations containing numbers, links, unknown references, physical-cause or deployment claims, or verdicts that contradict the recorded qualification; the recorded evidence analysis is then shown instead. AI cannot invent metrics, change results, train models or approve deployment. If it is unavailable, evidence analysis still works. Uploaded experiments require explicit, revocable consent before derived metrics are sent to OpenAI. Raw CSV rows, identifying labels and file paths are excluded. `store=False` does not remove the provider's possible abuse-monitoring retention.

On a hosted demo, set `SIDEKICK_ASSISTANT_PRESENTER_CODE` as a server secret to enable private presenter access. Public visitors receive evidence-only analysis. Live analysis allows one request at a time, with defaults of ten requests per presenter session and 25 per day. Free hosting can lose its local usage history on redeployment, so these limits are not a monthly billing cap. Replay mode never calls the provider. Set `SIDEKICK_ASSISTANT_LIVE_ENABLED=0` to disable cloud calls everywhere. `SIDEKICK_ASSISTANT_TASKS` (default `investigate,compare,warning,brief`) controls which analysis workflows are offered.

Routine tests use mocked provider responses. After changing the model or prompt, run the small live evaluation with `SIDEKICK_ASSISTANT_LIVE_EVAL=1` and a server-side key: `python scripts/evaluate_assistant.py`. It reports which cases passed verification and does not print the key.

## Evidence limits

The recorded benchmark is simulated NASA FD001 data. Logistic regression `lr2` warns 80/80 histories on clean readings but only 41/80 under its weakest required sensor dropout. Leading ordinary and augmented XGBoost both retain 79/80 in their weakest required case. This historical comparison does not isolate augmentation's effect.

V1.5 adds separately verified `lr2` replay traces without changing the original benchmark metrics. The older benchmark's tree models have only their originally stored examples. Historical FD001 histories remain exposed.

The default 70% detection, 10% alarm burden and 10-to-30-cycle warning window are demonstration settings. Faults are simulated and not calibrated to ABB field measurements. Development results also select thresholds and configurations. Bootstrap intervals are exploratory. Fresh reserved results still do not establish performance on real ABB equipment.

[Verification and remaining pilot work](TESTING.md)
