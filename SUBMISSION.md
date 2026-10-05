# Sidekick v1.5 reviewer handoff

## Suggested submission

**Title:** Sidekick: Stress-testing predictive maintenance models

**Description:** Sidekick checks whether equipment failure-warning models remain useful when sensor readings go missing, freeze or drift. Engineers define a protocol, train candidate models, inspect detection and alarm burden under simulated faults, and export the supporting evidence. The local app adds model freezing and a one-time evaluation on eligible reserved histories. A recorded NASA benchmark and a compact hosted synthetic sample demonstrate the workflow. No API key is required. ABB field performance remains unverified.

- Parent submission: existing Sidekick idea-phase entry.
- Theme: Theme 1 used for the parent submission.
- Repository: https://github.com/Havocx01/SideKick
- Public demo: https://sidekick-e9lu.onrender.com/
- Presentation: use the final deck, updated to distinguish development results from final validation.
- Snapshots: `media/submission/v1.5-01-start.jpg`, `v1.5-02-comparison.jpg`, `v1.5-03-replay.jpg`.
- Walkthrough recording: `media/submission/sidekick-v1.5-walkthrough.webm`. It demonstrates recorded evidence; it is not a newly executed NASA evaluation.
- Source: package this revision, excluding local datasets, environments, node_modules and artifacts. Keep the evidence, tests and documentation.

The public service needs deployment of this revision and a smoke check before it can be described as v1.5. The local app is the main presentation environment. Older videos and proposal files describe earlier versions.

## Run instructions

Use the README setup commands, then open http://127.0.0.1:8000. The built app can explore the benchmark and run synthetic experiments without internet access or an API key.

Choose **Set up sample**, generate the data and review the split. Keep the demonstration acceptance limits for the first run. You can change warning windows and required fault cases locally before training. Select **Train and challenge models**. When finished, inspect the comparison, Evidence guide and warning replay, then export the evidence ZIP or open the report.

Uploaded CSVs require at least 25 complete failure histories and explicit mapping. The hosted service accepts only its fixed synthetic sample, with quotas and temporary storage.

## Presentation walkthrough

1. Explain the question: will a failure warning still work when a sensor fails? Open **Start guided walkthrough** for the five-step recorded story. It never launches training or reserved scoring.
2. Open **Explore benchmark**. Say that it is recorded, simulated NASA data, not ABB field validation.
3. Inspect `lr2`: 80/80 clean detections falls to 41/80 under sensor 8 dropout. The bars separate warnings in time, late and missed. Open **Sensor faults** and click that heatmap cell for detection, burden, coverage and failure reasons.
4. Open **Replay weakest detection case**. This is now an `lr2` replay, verified against the stored benchmark metrics. Use Play/Pause and the cycle slider to show the original warning beside the faulted warning. Playback reads stored results; it does not rerun inference. The trace is a selected example, not fleet-wide performance.
5. Compare ordinary `xgb1` and augmented `aug3`: both retain 79/80 in their weakest required case. Do not claim a large causal improvement from augmentation.
6. Ask one Evidence guide question, follow its link and open the exported report. The inspected model is separate from the overall recommendation. Advanced comparisons, calibration and reproducibility are under **Technical details**.
7. Show a completed local synthetic experiment. Explain the 40 development histories, five folds and 20 reserved histories. Label an earlier run as an earlier run.
8. Show the matched-configuration comparisons. Detection and burden intervals use whole-equipment bootstrap resampling. They remain exploratory.
9. If demonstrating final validation, use eligible, previously unexamined reserved histories in a local dataset, complete development, freeze the selection, and confirm the reserved histories were not used for decisions. Score them once. Explain that an interrupted scoring attempt still exposes them. Previously examined NASA histories cannot serve as fresh validation.
10. Close with the next step: an engineer-agreed protocol and complete, representative field records from actual equipment.

For a failure outcome, try 100% useful detection and 0% early-alarm burden on the compact sample. No qualifying model is a valid result. Check the result during rehearsal; do not promise that every dataset produces the same outcome.

## Before using the public link

Deploy this revision to the existing free service, then check health, a hosted sample, refresh persistence, comparison, replay and ZIP export. A second browser must receive 404 for the first browser's experiment. Uploads, custom protocols, freezing and reserved scoring must remain disabled on the hosted service. Replay mode must reject all training.

The Linux test used a 512 MiB container and completed a compact sample below the 450 MiB working-set target. This is a local resource check, not a claim of Render uptime or identical hosted latency. The service can sleep and lose temporary results on restart; export them.
