# Sidekick

Investigate whether equipment-warning models still warn in time when sensors go missing, freeze or drift.

Sidekick combines NVIDIA Nemotron experiment proposals with deterministic sensor-fault evaluation. Engineers can reproduce failures, reduce them to simpler scenarios, compare remedies and export the evidence behind the next decision.

[Public demo](https://sidekick-e9lu.onrender.com/) · [Reviewer guide](SUBMISSION.md) · [Submission details](docs/nebius-submission.md) · [MIT license](LICENSE)

## Start here

**Explore without installing:** open the public demo and choose **Investigations** to inspect recorded synthetic investigations. These are labelled **Recorded, not live**. The hosted app also offers the earlier walkthrough and restricted sample training. New Nemotron searches, fault research, private uploads and full validation run locally.

**Run on Windows:**

1. Download the [main-branch ZIP](https://github.com/Havocx01/SideKick/archive/refs/heads/main.zip) and extract it.
2. Install Python 3.11+ and Node.js 22.12+ or 20.19+ if they are not already available.
3. Double-click **Start Sidekick.cmd**. It prepares dependencies, builds the interface and opens [localhost:8140](http://127.0.0.1:8140).

Keep the launcher window open; Ctrl+C stops the server. The first launch needs internet. On macOS or Linux, run `python3 scripts/launch.py`. No API key is needed for recorded evidence or local training. Restart the app after changing server settings.

To prepare a complete local investigation, run this from the extracted project after setup:

```powershell
.venv\Scripts\python.exe scripts/demo_investigation.py
```

Then open **Investigations** and select the saved concern beginning **Demo: find sensor faults**. The command trains a synthetic fixture, evaluates supplied cases, reproduces and reduces a failure, compares a threshold remedy, assesses a frozen procedure on fresh synthetic histories and exports public evidence. It makes no provider calls. Its 0.95 warning threshold is deliberately fragile so the demonstration contains a failure; it is not a recommended setting. With the Nebius key in `.env`, add `--allow-nebius` to let Nemotron propose further cases within 4 calls and 16,384 completion tokens.

## Investigation workflow

1. Choose a fitted development context and model, review clean performance, and set the criterion, profile and experiment limits.
2. Run supplied proposals locally, or explicitly allow **Start Nemotron search**. Nemotron receives the concern, channel aliases, reviewed descriptions, bounds and aggregate results.
3. Inspect matched clean/faulted useful warnings, lead time, early alarm burden, coverage and exclusions. Code classifies findings; model explanations remain hypotheses.
4. Replay a result, reduce a measured failure, compare a threshold change or explicitly approved augmented retraining, and export a regression case.
5. Freeze the chosen procedure before assessing fresh histories. Previously exposed histories cannot become a new independent holdout.
6. Optionally choose **Research this fault** to retrieve external references through Tavily and ask Nemotron for cited follow-up suggestions. Research is separate from measured findings.

The runner saves proposals, canonical scenario IDs, attempts, checksums, call/token allowances and lifecycle events in SQLite. Duplicate requests, reopening a page or restarting the server do not reset paid-work counters. Cancellation and lease checks control publication. A saved model stop is not proof of robustness.

## NVIDIA, Nebius and Tavily

The investigation model is **`nvidia/nemotron-3-super-120b-a12b`**, served through **Nebius Token Factory**. The OpenAI Python SDK provides compatible transport; Nemotron proposes the experiments. Token Factory supplies hosted inference without a separate model-serving deployment. We have not established a development-speed improvement numerically.

Create a local `.env` from [.env.example](.env.example), then configure:

```dotenv
SIDEKICK_MODE=full
SIDEKICK_ASSISTANT_PROVIDER=nebius
SIDEKICK_ASSISTANT_MODEL=nvidia/nemotron-3-super-120b-a12b
SIDEKICK_ASSISTANT_LIVE_ENABLED=1
NEBIUS_API_KEY=
TAVILY_API_KEY=
```

Fill in your own server-side keys; Tavily is optional. Keep `.env` out of Git. Enable workspace AI permission and approve the specific action in the interface. Setting a key or opening a saved investigation never starts inference. Shell environment variables override `.env`.

Each fault-research action permits one Tavily search and one Nemotron request, with a total completion ceiling of 5,120 tokens. Saved research, including a failed or interrupted attempt, is reused without automatic paid retries. Source excerpts are untrusted context; citations do not prove a physical cause or validate a fault policy. The initial live search returned unrelated pages and the model declined sensor-specific advice. The final filter rejects those captured sources offline; useful live retrieval remains unverified.

Token Factory is the default and only live model provider. No OpenAI account or key is needed; the OpenAI SDK is used only for compatible transport to Nebius. See the [provider setup guide](docs/nebius-phase-1.md). Containerized experiment workers are implemented, but deployment on Nebius Serverless Jobs or Endpoints is not claimed.

## Recorded results and limits

These are historical synthetic results tied to their saved fitted contexts, not guarantees for a newly trained model:

| Recorded evaluation | Result |
| --- | --- |
| [Live Nemotron investigation](evidence/investigations/nemotron-live-recorded.json) | Three accepted proposals, each evaluated on 22/22 histories. Later proposals referenced earlier results. No qualifying failure; 1,083 reported completion tokens. |
| [Supplied compound-fault demonstration](evidence/investigations/compound-demo-recorded.json) | At the deliberately fragile 0.95 threshold, stuck vibration and oil-particle channels reduced useful warnings from 22/22 to 8/22. The case replayed and was reduced. It was supplied, not discovered by Nemotron. |
| [Fresh synthetic assessment](evidence/investigations/fresh-validation-recorded.json) | On 12 fresh histories, a 0.5 threshold remedy changed reduced-case useful warnings from 8/12 to 12/12. The stronger original case improved from 0/12 to 5/12 and still failed. |
| [Automatically selected thresholds](evidence/investigations/synthetic-recorded.json) | None of six supplied cases met the failure criterion. |

The project includes fixed, random, hill-climbing and recorded-Nemotron search comparisons. The available live comparison does not establish that Nemotron outperforms simpler search.

The earlier NASA C-MAPSS evidence demonstrates the original single-sensor workflow. It is simulated-engine evidence and already exposed. Neither those results nor the synthetic investigations establish ABB field performance, maintenance savings or deployment approval. Fault-profile relationships are declared prototype assumptions until independently supported.

## Development and reproducibility

The stack is React/TypeScript/Vite, Python/FastAPI/Pydantic, SQLite, NumPy, pandas, SciPy, scikit-learn and XGBoost. The project includes browser and API workflows, a CLI, private trusted replay packages and separate aggregate public exports.

- `tasks.ps1 web` starts frontend development; `tasks.ps1 api` serves the built app locally. `make` equivalents are available.
- `docker compose up --build` starts local development services at [localhost:5173](http://localhost:5173).
- Deployment contexts, coordinators and remote workers use Python 3.11.9 on Linux with [pinned numerical dependencies](docker/runtime-constraints.txt). Native Windows packages are not assumed to replay identically on Linux.
- Contexts are bound to their source and dependencies. Old fitted contexts are excluded from new-run selection; their saved investigation records remain readable. Generate a new context after source changes.
- Full mode is a local workspace. Publishing it remotely requires an authentication and ownership boundary beyond the restricted hosted demo.

See [verification commands](TESTING.md), [compound evaluation](docs/nebius-phase-2.md), [investigation API/CLI and research](docs/nebius-phase-3.md), and [backup and recovery](docs/workspace-backup.md). Routine tests run offline. Paid inference requires an explicit live action.

## Earlier project and hackathon updates

Sidekick V2 began as an ABB Accelerator 2026 project for comparing equipment-warning models under fixed single-sensor faults. The Nebius x NVIDIA adaptation adds compound evaluation, a durable adaptive controller, fault profiles, findings, reduction, remedies, search comparisons, a browser/API workbench, fresh-history validation, recorded public evidence and optional Tavily research. [Submission details](docs/nebius-submission.md) distinguish the earlier work, new implementation and verified results.

The project is licensed under [MIT](LICENSE). Dataset and dependency terms still apply to their respective materials.
