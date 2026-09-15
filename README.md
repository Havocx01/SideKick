# Sidekick

A predictive-maintenance copilot for **ABB Accelerator 2026**, built by Adam Qablawi and Kareem Massoud. It evaluates whether equipment-failure models still give useful warnings when sensor data becomes unreliable.

## My work

- Built the React/FastAPI copilot, connecting MLflow results to LLM-assisted evidence reviews so engineers could inspect failure warnings and false alarms before deployment decisions.
- Implemented a **5-stage validation workflow** on NASA C-MAPSS FD001, testing **3 prediction approaches** under missing or stuck readings and sensor drift to compare model reliability under faulty inputs.

## Evaluation

The workflow compares warning timelines and counts missed failures alongside false alarms. Separate machine-learning models make the predictions; the LLM explains recorded results.

## Repository

The implementation is in a private repository. This public repo contains the original proposal.

[Proposal (PDF)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.pdf) | [Editable proposal (Word)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.docx)
