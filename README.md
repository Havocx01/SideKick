# 🦸‍♂️ Sidekick

*Predict equipment failures. Challenge the predictions. Decide with evidence.*

Sidekick is a predictive maintenance copilot proposed for the **ABB Accelerator 2026**. It helps engineers stress-test equipment failure models to ensure they still provide useful warnings—even when sensor data becomes unreliable or goes offline.

## 🛠️ How It Works

1. **📊 Upload & Inspect:** Bring in your sensor histories and check the data quality.
2. **🧠 Train & Compare:** Build and evaluate different failure prediction models side-by-side.
3. **🌪️ Stress Test:** Throw chaos at the models—missing readings, stuck sensors, and data drift.
4. **🔄 Retrain & Measure:** Simulate faults, retrain the models, and see if the new data improves performance.
5. **⚖️ Review & Decide:** Analyze warning timelines, missed failures, and false alarms before deciding what to take to trial.

*Note: The copilot guides the workflow and explains recorded results, while separate machine learning models handle the predictions. **Deployment decisions always stay with the engineer.***

## 🚀 Planned Prototype

- **Dataset:** NASA C-MAPSS FD001 data for an initial simulation-based evaluation.
- **Models:** Logistic Regression and XGBoost, benchmarked against a simple equipment-age baseline.
- **Tech Stack:** ⚛️ React (interface), ⚡ FastAPI (backend), and 📈 MLflow (experiment tracking).
- **AI Copilot:** An existing LLM to coordinate tools and answer questions about the generated evidence.

## 🚧 Status

Sidekick is currently an **idea-phase** project. 💡 This repository contains the official proposal; implementation and measured results are still to come. *(Keep in mind: Tests on simulated data will not immediately establish readiness for a working, live plant.)*

## 📄 Proposal

- 📕 [Read the proposal (PDF)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.pdf)
- 📘 [Editable proposal (Word)](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.docx)

## 🤝 Team

Built by **Kareem Massoud** and **Adam Qablawi**.
