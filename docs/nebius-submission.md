# Nebius x NVIDIA submission notes

Track: **Best Apps and Agents**.

## What it is

Sidekick is an investigation workbench for engineers who must decide whether an equipment-warning model can tolerate unreliable sensors. An engineer chooses a fitted model, states a concern and sets bounds. Nemotron proposes sensor-fault experiments. Sidekick runs them against fixed development models, classifies each result with deterministic code, reduces failures to simpler reproducible cases and measures what a remedy fixes and what it costs elsewhere.

Audience: reliability and data engineers selecting a warning model for one equipment family. Decision supported: which model and warning rule to take to a supervised trial, and which sensor failures to plan for.

## How it is built

- **Model:** `nvidia/nemotron-3-super-120b-a12b` through Nebius Token Factory's OpenAI-compatible Chat Completions API, with strict JSON-schema output, explicit `reasoning_effort` and a reserved reasoning budget. Token Factory is the only Nebius service used. Serverless Jobs and Endpoints were not needed for these small tabular models.
- **Controller:** sends Nemotron aliased channels, reviewed profile descriptions, fault bounds, clean performance and aggregate results. Nemotron returns one proposal with a hypothesis, or a stop reason. Local validation, durable call and token limits, leases and consent decide what runs.
- **Engine:** a fixed development evaluator scores bounded compound sensor corruptions on matched clean and faulted histories. It is backed by finding criteria, versioned fault profiles, a reducer, remedy comparisons, a search benchmark and checksummed remote worker jobs.
- **Surfaces:** a CLI, an owned HTTP API with background workers, and a React workbench. Public evidence exports exclude private data.

## Earlier project and new work

Sidekick V2 (ABB Accelerator 2026) already trained and compared models on single-sensor faults. The adaptation started at `4c956f0` (27 October 2026, Nebius provider support). The commits from `813fa52` onward (28–29 October 2026) add, in order:

- the compound evaluator, the runner and the Nemotron controller
- finding criteria, fault profiles, adaptive context, reduction and remedies
- the benchmark, the HTTP API, the browser workbench and remote workers
- public evidence and failure-injection verification

`git log 4c956f0^..HEAD` lists every change.

## Measured results

The initial Windows live check on 30 October 2026 authenticated successfully and made two Nemotron calls. Both responses were rejected by local scenario validation before execution; 864 completion tokens were reported and no experiment ran. The observed reply combined explicit onsets with random seeds, supplied inapplicable fault parameters and crossed declared sensor groups. Prompt v4 states those constraints explicitly.

A separately authorized two-call check with prompt v4 reported 539 completion tokens. One reply was rejected because its transient fault had no length. The other passed validation, reached the evaluator and was saved, verifying the live proposal-to-saved-result path. Its onset was 100 cycles before failure, outside all 22 development histories, so the result was `not_applicable` with zero evaluated histories and no measured failure. The saved result passed its checksum check, replayed exactly without provider calls and exported as aggregate evidence. A useful live measurement remains unverified; timing bounds need to reflect the fitted development histories, and provider schemas should express fault-specific parameter requirements.

The recorded offline results below come from local, deterministic evaluation on synthetic data. Real equipment, ABB field performance and maintenance savings are not established; exact learned-model counts belong to their recorded fitted contexts.

- **Fixed-threshold demonstration** (`scripts/demo_investigation.py`; 22 development histories; logistic model at a deliberately fragile 0.95 threshold):
  - 1 of 5 cases was a measured failure: stuck vibration plus particle count, with useful warnings falling from 22/22 to 16/22 (100% → 73%).
  - It replayed exactly and reduced to later onsets. It is component-minimal and minimal only on the tested grid.
  - A 0.5 threshold remedy fixed 2 cases (the failure and its reduction) and degraded none, with clean burden unchanged.
- **Search benchmark** (budget 24, 2 thresholds × 5 seeds = 10 runs per strategy): random search found 3 failure families in 2 of 10 runs; the fixed suite and hill climber found none. The Nemotron controller is not yet in this comparison, because that needs recorded live runs.
- **Default synthetic package** (`evidence/investigations/synthetic-recorded.json`): 0 of 6 cases failed at automatically selected thresholds.

## Still needed from the owner

- A bounded live run that scores eligible histories after tightening timing bounds and structured proposals: `docs/nebius-phase-3.md` → Live smoke run. Preserve both existing captures and use a fresh context and investigation after source changes. Then add verified Nemotron runs to the benchmark with `--recorded`.
- The demo URL, a public video of at most three minutes, and Nebius/NVIDIA feedback based on that live usage: structured output, reasoning controls, latency, errors.
