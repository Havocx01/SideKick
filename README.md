# Sidekick
A predictive-maintenance copilot proposal for **ABB Accelerator 2026**, by Adam Qablawi and Kareem Massoud. Sidekick will evaluate whether equipment-failure models still give useful warnings once sensor data becomes unreliable — and whether retraining on corrupted data can fix that.

## Status
This repo currently holds our submitted idea-phase proposal. The build window runs 18–28 Sep; nothing below is implemented yet.

## Planned work
- A React/FastAPI copilot connecting MLflow run results to LLM-assisted evidence reviews, so engineers can inspect failure warnings and false alarms before relying on a model.
- A validation workflow on NASA C-MAPSS FD001 testing three prediction approaches (logistic regression, XGBoost, and an XGBoost variant retrained on corrupted sensor data) against dropout, stuck-sensor, and drift faults.

## Evaluation approach
The workflow will compare warning timelines and count missed failures alongside false alarms. Separate ML models make the predictions; the copilot explains recorded MLflow results — it does not generate its own numbers.

## Repository
The implementation will live in a private repo during the build window. This public repo holds the original proposal.

[Proposal (PDF)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.pdf) | [Editable proposal (Word)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.docx)
