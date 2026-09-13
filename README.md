# Sidekick

Predict equipment failures. Challenge the predictions. Decide with evidence.

Sidekick is a predictive maintenance copilot proposed for ABB Accelerator 2026. It helps engineers check whether an equipment failure model still gives useful warnings when sensor data becomes unreliable.

## How it works

1. Upload sensor histories and check the data.
2. Train and compare failure prediction models.
3. Test them against missing readings, stuck sensors, and sensor drift.
4. Retrain with simulated faults and measure whether it helps.
5. Review warning timelines, missed failures, and false alarms before deciding what to trial.

The copilot guides the workflow and explains recorded results. Separate machine learning models predict equipment failures. Deployment decisions stay with the engineer.

## Planned prototype

- NASA C-MAPSS FD001 data for an initial simulation-based evaluation.
- Logistic regression and XGBoost models, compared with a simple equipment-age baseline.
- React interface, FastAPI backend, and MLflow experiment tracking.
- An existing LLM to coordinate tools and answer questions about the evidence.

## Status

Sidekick is currently an idea-phase project. This repository contains the proposal; implementation and measured results are still to come. Tests on simulated data will not establish readiness for a working plant.

## Proposal

- [Read the proposal (PDF)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.pdf)
- [Editable proposal (Word)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.docx)

## Team

Kareem Massoud and Adam Qablawi.
