# Investigation records

Investigation setup, experiment execution and provider-call limits are saved locally. Nemotron can choose the next fault scenario from aggregate results, while the local validator and fixed evaluator control execution and measurements.

Given an existing `FixedDevelopmentEvaluator` and `backend` on the Python module path:

```python
from pathlib import Path
from app.investigator.records import InvestigationBudget, InvestigationStore

store = InvestigationStore(Path("output/investigations"))
budget = InvestigationBudget(max_experiments=8, max_proposals=16, max_seconds=300)
record = store.create(evaluator, objective="Find missed warnings under combined measurement faults.", budget=budget)
loaded = store.get(record.id)
loaded.check_context(evaluator)
```

`investigator.sqlite3` stores the objective, fixed context/config fingerprints, fault policy, model thresholds, budget and creation event. Records survive restart; they do not contain fitted models or copied sensor histories. Objectives may contain private user text.

The experiment cap cannot exceed the evaluator policy. `check_context` rejects a different evaluator; the caller must supply the original fitted context. The record alone cannot reconstruct it.

Setup, validation, status and ordinary runner actions stay local. The explicit controller and fault-research actions make provider requests. The Python record interface below is also exposed through the owned HTTP API described later in this guide.

## Scenario proposals

`ScenarioProposal` contains a `scenario` using the existing `FaultCase` contract and a short `reason`. It can be used as the existing provider adapter's response model. The reason is unverified model text, not measured evidence or an instruction to execute.

```python
from app.investigator.proposals import validateProposal

proposal = validateProposal(responseJson, loaded, evaluator)
scenarioId = proposal.scenario.scenario_id
```

Validation accepts JSON text up to 16 KiB. It rejects extra fields, incorrect types, empty reasons, invalid fault parameters, unknown sensors and violations of the investigation's component/group/timing/severity bounds. The record is revalidated and must match the evaluator's fixed context. Scenario IDs are computed locally from canonical parameters.

This check does not determine whether a fault changes scorable readings; the evaluator reports actual applicability and coverage. Validation alone neither saves proposals nor consumes budget.

## Experiment runner

The runner shares `investigator.sqlite3` with the record store. Add execution state to an existing record without replacing its objective, policy or limits:

```python
from app.faults.investigation import ExperimentRunner, InvestigationStore

runnerStore = InvestigationStore(Path("output/investigations"))
runnerStore.attachRecord(loaded.id)
runnerStore.add_proposals(loaded.id, [proposal.model_dump(mode="json")])
summary = ExperimentRunner(runnerStore, evaluator).run(loaded.id)
```

The runner checks context and policy, validates proposals through `validateProposal`, skips duplicate scenario IDs and reserves a slot transactionally before execution. Bare `FaultCase` inputs are also accepted for CLI compatibility and labelled as imported scenarios. Rejected proposals and duplicates use no experiment slots; they still count toward the saved proposal limit.

Each started attempt consumes a slot, including failures, timeouts, interruptions, cancellation and run-time stops. Pre-start cancellation or an expired deadline releases the reservation. Failed scenarios are retried after untried scenarios, up to the per-scenario attempt limit and total failure limit. Completed results have checksums and must match their scenario, policy and fitted context when saved or read.

The run-time limit applies to each `run()` invocation and cannot exceed the saved record's `max_seconds`. Experiment/proposal limits persist across invocations. Cancellation and deadlines are cooperative: a long model-scoring call cannot be forcibly interrupted. A lease prevents concurrent runners for the same investigation. After an abrupt process crash, recovery waits for lease expiry (the evaluator's time limit plus 60 seconds), marks started work interrupted and releases unstarted reservations. A runner that loses its lease cannot save results.

For a trusted context exported with the current source and dependency versions:

```powershell
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --context output/context-package --trust-local-artifact --create proposals.json
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --context output/context-package --trust-local-artifact --run <id>
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --status <id>
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --cancel <id>
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --resume <id>
```

`proposals.json` is a JSON list of typed proposals, bare cases or raw JSON strings. `--attach <id>` enables execution for an existing record in the same store; `--add <id> proposals.json` appends proposals. `--create` accepts an objective and experiment/failure/attempt/run-time limits. Loading a context rechecks its recorded evaluation before new work and requires explicit local artifact trust. The ordinary runner does not train or call a provider.

## Nemotron controller

Configure Nebius using the [provider setup](nebius-phase-1.md). The controller requires full mode, enabled live inference and an NVIDIA Nemotron model. For an existing investigation, run:

```powershell
.venv/Scripts/python.exe scripts/run_fault_investigation.py --store output/investigations --context output/context-package --trust-local-artifact --agent <id> --allow-nebius --max-provider-calls 2 --max-completion-tokens 10240
```

`--allow-nebius` approves billable requests for that invocation, separately from browser permissions. The objective is sent verbatim, alongside aliased sensor/model names, numeric fault bounds and aggregate matched results. Raw sensor histories, equipment IDs, fitted objects, API keys and private policy notes are excluded from the packet. Recent cases are limited to twelve, with an explicit omitted count.

Nemotron returns one typed proposal or a stop reason. Channel aliases are mapped locally and checked by `validateProposal`. Accepted proposals are saved atomically with their provider-call record, then evaluated before the next request. Pending proposals recovered after interruption run before another provider request. Only server-computed metrics enter the result summaries; model reasons and stop explanations remain unverified text.

Provider call and completion-token reservations persist across restarts. Errors and interrupted calls retain their reservations, and the SDK makes no retries. Per-call completion limits include the configured reasoning headroom; the cumulative completion limit counts those full ceilings, not actual usage. Input content and schema have a separate byte limit. These controls bound execution allowances; actual provider usage, input-token charges and pricing are separate.

Each call also records the provider's request ID, reported token usage and elapsed time; `--status` shows them with `reportedCompletionTokens` next to the reserved ceiling. Add `--capture output/live-capture.json` to an `--agent` run to save the commit, controller configuration (endpoint, model, prompt version, reasoning effort, limits), per-call records and the final report. The capture contains no key, objective or raw data.

### Proposal contract

Nemotron answers in a provider-specific shape where invalid combinations cannot be written. Each component is either a drift fault (`severity_sd`, `sign` of -1 or 1, `ramp_cycles`) or a loss fault (`dropout` or `stuck`, with no drift fields). Its `onset` is `{"mode": "explicit", "onset_before_failure": n}` or `{"mode": "seeded", "seed": n}`, and its `duration` is `{"mode": "persistent"}` or `{"mode": "transient", "length": n}`. The schema uses only `$defs`, `$ref`, `anyOf`, `enum` and numeric bounds, which Token Factory accepted in the October 2026 live runs. Accepted replies are converted to the existing `ScenarioProposal` and `FaultCase` models, so strict local validation, stored proposals and identities are unchanged. Prompt version: `nemotron-fault-search-v5`.

The model input includes `timing`, computed from the fitted development histories after feature-window warmup: how many histories each explicit onset reaches, and the furthest reachable onset, which also caps `bounds.maxOnset`. Before a proposal can use an experiment slot, an applicability preview injects it into every development history without scoring or using the evaluation budget. A case that changes no scorable readings in any history is rejected with the most common reason (for example "channel-1: history never reaches 100 cycles before failure"). Cases with partial coverage still run, and the evaluator's coverage stays authoritative.

A reply in the wrong shape, an unknown alias, a policy violation or an inapplicable case is saved as a rejected call. Its `feedback` is a reason of up to 300 characters, made only from local validation messages with sensor names replaced by aliases. The next call sees it in `recentCalls`. Corrections use the saved call and token allowance and survive restarts. Non-JSON or truncated replies still stop the run as `invalid_response`. `tests/test_proposal_contract.py` replays the captured live replies offline.

### Search context

Each request starts from clean performance: every fixed model's detection and alarm burden on all development histories. Each completed experiment gets a stable `result-N` ref, its family (sensor and fault-kind combination, ignoring timing and severity) and, when a criterion is saved, its finding status. A family table (up to 24, with an omitted count) gives experiments, measured failures and the worst detection change for every family tested so far. The rejected-proposal count and the last three validator reasons are included. Full detail is kept for the latest twelve cases, so the input stays bounded however long the run.

A proposal may include a hypothesis: what is suspected, what measurement would support it, what would weaken it, and the `result-N` refs it builds on. Refs are mapped to real attempt IDs before saving; an unknown ref rejects the proposal. Hypotheses are stored as unverified model text, separate from measured results. `--findings` reports `discoveryFamilies`, so many severities of one combination count as one discovery.

`--create … --seed N` prepends up to N deterministic single-channel cases, choosing one channel from each declared group first, so the first measurements span the profile before the model chooses.

### Live smoke run

From the repository root on Windows, with `NEBIUS_API_KEY` and `SIDEKICK_ASSISTANT_PROVIDER=nebius` in `.env`:

```powershell
.venv\Scripts\python.exe scripts/evaluate_fault_scenarios.py --profile synthetic-rotating-v1 --output output/live-context
'[]' | Out-File -Encoding ascii output/empty.json
'{"candidate": "logistic_regression/lr-probe"}' | Out-File -Encoding ascii output/criterion.json
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --context output/live-context --trust-local-artifact --create output/empty.json --criterion output/criterion.json --max-experiments 4 --objective "Find sensor faults that cost useful warnings."
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --context output/live-context --trust-local-artifact --agent <id> --allow-nebius --max-provider-calls 4 --max-completion-tokens 16384 --capture output/live-capture.json
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --context output/live-context --trust-local-artifact --replay <id>
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --public-export <id> output/live-evidence.json
```

The run uses synthetic data only and makes at most four billable calls within 16,384 reserved completion tokens. `--replay` reruns every completed experiment without provider calls and reports whether each matches its saved evidence; it needs the same source and runtime that made the context. `scripts/demo_investigation.py --allow-nebius` runs the full story with the same allowance. The separate `check_nebius.py --live` probe makes additional paid calls and is not part of this sequence. A failed call is still captured; it is evidence, not a completed end-to-end test. Preserve previous captures, and use a fresh context and investigation after a source or prompt change.

The controller holds the runner lease while the model thinks. Cancellation and the saved run-time deadline also apply while awaiting a provider response. Another runner cannot execute the same investigation concurrently, and a lost lease cannot publish a reply. Local validation failures can lead to a new proposal within the remaining limits; malformed responses and provider errors stop the invocation. Changing the saved model, endpoint, prompt or limits requires a new investigation. Rotating a key does not reset counters.

`--status <id>` shows controller configuration, reservations and call outcomes without a key or model context. The final controller report includes cumulative calls/experiments used and result references. A model stop is not evidence that all failure modes were tested. Reduction, remedy comparisons, search baselines and the browser workbench are described below.

## Finding criteria

A finding is the server's classification of a recorded result. It is computed only from a saved evaluation and a saved, versioned criterion, so the same evidence always gets the same classification, and no provider call is involved. Nemotron's reasons remain hypotheses; findings are measurements.

Save the criterion with `--create proposals.json --criterion criterion.json` (or `--attach ID --criterion …`, or later with `--set-criterion ID criterion.json`). A criterion is fixed for its investigation; a different one needs a new investigation so earlier findings stay comparable.

```json
{
  "version": 1,
  "candidate": "logistic_regression/lr-probe",
  "min_coverage": 0.8,
  "min_histories": 10,
  "min_clean_detection": 0.8,
  "min_lost_warnings": 1,
  "max_alarm_burden": 0.05,
  "min_burden_increase": 0.01
}
```

Only `candidate` is required; it must be one of the investigation's fixed models. The other values above are the defaults.

`--findings ID` classifies every rejected proposal and finished experiment, saves the classifications and prints them. It needs no model context or key. Outcomes:

- `measured_failure` is the only discovery. On matched clean and faulted histories, at least `min_lost_warnings` useful clean warnings became missed or late (`missed_warnings`, `late_warnings`), or the early alarm burden rose by at least `min_burden_increase` to above `max_alarm_burden` (`alarm_burden`).
- `no_measured_failure` means coverage and clean behavior were adequate and no effect met the criterion. It is not evidence of robustness beyond the tested scenario.
- `inconclusive` means coverage is below `min_coverage` or `min_histories`, the clean model misses `min_clean_detection` or already exceeds `max_alarm_burden`, or burden is unavailable. Observed effects are still listed, but they do not count.
- `not_applicable` means no eligible history had changed scorable readings.
- `invalid_proposal` and `execution_error` record rejected proposals and failed, timed-out or interrupted experiments.

Each finding stores the criterion and its fingerprint, the evaluation's SHA-256 digest, scenario and context identities, coverage, absolute clean and faulted detection and burden, the effects with supporting equipment IDs, and every matched history whose warning state, lead or episode count changed. Re-running `--findings` recomputes each classification and rejects a saved finding that no longer matches its evidence.

## Reduction

`--reduce <attempt-id> --context … --trust-local-artifact` simplifies a measured failure. It needs a saved criterion and holds the investigation lease. Steps:

1. Rerun the original case. If it is no longer a measured failure, the reduction stops as `not_reproduced`.
2. Try removing each component, keeping a removal only if the finding still holds, until no single removal preserves it.
3. For each remaining component, try explicit ascending grids: lower drift severity (0.5–3 SD), shorter transient length (5–80 cycles) and later onset (10-cycle steps). The first passing value is the smallest passing value on that grid, without assuming the outcome is monotonic. Drift ramps are not shortened, because a shorter ramp is more abrupt rather than simpler.

Every attempt is saved with its change, case, finding status, evidence digest, evaluated-history count and whether the matched cohort changed. Reduction has its own allowance (`--max-reduction-experiments`, default 16); cached cases are free. It never adds proposals, attempts or findings to the investigation, so a family is still counted once. Outcomes are `complete`, `partial` (allowance used up), `cancelled`, `interrupted` or `not_reproduced`. Claims only cover what was tested: "component-minimal under tested single-component removals", "minimal on the tested grid for …", and always "not a proof of a global minimum".

`--regression <reduction-id> file.json` exports the final case with its criterion, expected status, context and policy fingerprints, profile and source IDs. `--remedy … --regressions file.json` reruns it and refuses a different fitted context or policy.

## Remedies

`--remedy <id> threshold --threshold 0.5` or `--remedy <id> augmented --approve-training` compares a remedy against the original fixed context. Remedies:

- `threshold` reuses the same fitted models with an explicitly chosen warning threshold for the target model. It is an explicit candidate change, so it has its own context fingerprint.
- `augmented` retrains the same development folds with sampled sensor-fault augmentation and selects its threshold on clean out-of-fold predictions. Training needs `--approve-training` and never reads reserved histories.

The comparison reruns every discovered case, every finished reduction, any regression files (`--regressions a.json b.json`, which must match the context and policy) and every other tested case. For each case it reports the original and remedy finding status, evaluated histories, exclusions, clean and faulted detection and burden, faulted median lead, and whether the matched cohort is the same. `improved` counts failures that became `no_measured_failure` on the same cohort. `degraded` counts previously passing cases that now fail. Clean performance on all development histories is shown for both. `meetsCriteria` means the remedy's clean detection and burden satisfy the saved criterion and nothing degraded. Preparation and evaluation time are recorded as cost.

Reports are saved in the store. They are development-only and were chosen using these cases, so a promising remedy needs fresh validation. Nothing replaces a deployed model.

## Independent validation

Discovery, reduction and remedy choice all use the same development histories, so their results are exploratory. Validation keeps them apart:

```powershell
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store <store> --freeze <id> --threshold 0.5
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store <store> --context <package> --trust-local-artifact --validate <validation-id> --fresh fresh.csv
```

- `--freeze` records the procedure before any fresh history is read: every discovered case, every finished reduction, the finding criterion, the optional threshold remedy, and the context, policy, model and prompt identities. The record carries a digest.
- `--validate` assesses that frozen procedure once. Models are refit on all development histories and score only the fresh ones; the clean comparison and every frozen case are classified with the saved criterion.
- An exposure ledger in the investigation store holds every history ever read: the development histories, the NASA FD001 identities in `evidence/history-identities.json` and every fresh set. Identity is content, not name, so renaming a history does not make it fresh. Fresh histories enter the ledger before scoring, so an interrupted assessment still uses them up.
- A procedure is assessed once. Freezing a changed procedure is allowed, but it needs another set of fresh histories.

`--fresh-synthetic SEED` generates fresh synthetic histories for demonstrations. Previously inspected NASA results cannot become a sealed holdout.

## Search benchmark

`scripts/benchmark_search.py --output report.json` compares search strategies on the synthetic fixture. With `--recorded <store> <id> --context <package> --trust-local-artifact`, it instead compares a saved Nemotron run on that run's own context, criterion, experiment allowance and supplied cases, and the baselines run under the same terms. Every strategy gets:

- a fresh evaluator for each run, so no strategy reuses another's cache
- the same profile and the same finding criterion
- the same three seed cases, which count toward the budget
- the same experiment budget (`--budget`, default 24)

Each strategy runs once per context (`--thresholds`) and seed (`--seeds`). Strategies:

- `fixed`: every permitted single-channel fault at the warning horizon, in order.
- `random`: constrained random sampling within the profile's groups, kinds, severity caps and onsets.
- `climb`: (1+1) hill climbing on a discrete encoding. It changes one onset, one severity or one kind, or adds or drops one channel in the same group, around the case with the largest detection drop, never repeats a tested case, and restarts at random one time in five.
- `nemotron` (with `--recorded`): the saved controller run as it happened. Nothing is re-executed; every call, rejected reply, duplicate, failed execution, reported token and reduction experiment counts.

Infeasible proposals, duplicates and failed executions are counted. Each run reports discoveries, discovery families (the dedup rule is stated in the report), experiments to the first discovery, the strongest detection drop, the most lost warnings, mean coverage, families tested, feasibility rate, elapsed time and provider calls. Results are out-of-fold development evidence; findings chosen adaptively are exploratory.

On the synthetic fixture (budget 24, five seeds, thresholds 0.95 and 0.9; `evidence/benchmarks/synthetic-fixture.json`), `random` found 5 discovery families in 6 of 10 runs, `climb` 2 families in 1 of 10 and `fixed` none. The climber has no signal to follow when early cases change nothing, so random sampling did better here. That is the result to report. The recorded Nemotron comparison is in `evidence/benchmarks/nemotron-default-context.json`.

## HTTP API

In local full mode, `/api/investigations` exposes the same engine through background workers. Fitted contexts come only from the server's registry folder, `artifacts/investigations/contexts/<name>/`. Create one with:

```powershell
.venv\Scripts\python.exe scripts/evaluate_fault_scenarios.py --profile synthetic-rotating-v1 --output artifacts/investigations/contexts/synthetic
```

Browser uploads are never loaded as contexts. Hosted demo and replay modes return 403.

| Operation | Route |
| --- | --- |
| List contexts with clean performance | `GET /api/investigations/contexts` |
| Create (context, objective, limits, criterion, seed cases, proposals) | `POST /api/investigations` |
| List or read your investigations | `GET /api/investigations`, `GET /api/investigations/{id}` |
| Start the runner or Nemotron controller | `POST /{id}/start` with `requestId`, `mode` (`run` or `agent`), `allowProvider` |
| Cancel, or clear a cancellation | `POST /{id}/cancel`, `POST /{id}/resume` |
| Reduce a measured failure | `POST /{id}/reduce` with `requestId`, `attempt`, `maxExperiments` |
| Compare a remedy | `POST /{id}/remedies` with `requestId`, `kind`, `threshold`, `approveTraining` |
| Replay a saved result | `POST /{id}/results/{attempt}/replay` |
| Export everything shown | `GET /{id}/export` |

How the API behaves:

- Each investigation records its owner, context and lifecycle events; another workspace gets 404 for reads and starts.
- A start, reduction or remedy runs once per `requestId`, so refreshing or retrying never starts duplicate paid work. Only one operation runs per investigation at a time (409 otherwise).
- Events are saved before they are shown. After a server restart, unfinished operations are marked `interrupted`; starting again recovers them within the saved limits.
- Agent runs need `allowProvider` and the workspace's provider permission. Revoking that permission stops the run, and a reply that arrives afterwards is not saved.
- The frontend types are generated from these models.

## Browser workbench

In local full mode, **Investigations** in the sidebar lists the fitted contexts and saved investigations.

1. Choose a context and the model under test, review its clean performance and profile, then set the concern, experiment budget and seed cases.
2. On the investigation page, choose **Run saved proposals** (local only) or **Start Nemotron search**. The search panel states what is sent to Nebius and what never is. It needs the consent checkbox, workspace AI permission, a call limit and a completion-token ceiling.
3. Watch the timeline: lifecycle events, provider calls with reported tokens and time, and every proposal with its status, rejection reason and unverified hypothesis.
4. Each finding shows coverage, clean and faulted detection and burden, its effects, the matched histories that changed and the profile assumptions it relies on. **Replay** reruns it; **Reduce** simplifies a measured failure.
5. Compare a threshold remedy, or approved augmented retraining, and export everything shown as JSON.

Opening a saved investigation never starts work. The page polls only while an operation is running, and keeps its inputs across refreshes. Cancelled, interrupted, failed, budget-exhausted and provider-error states are each shown separately. Reserved token ceilings are labelled as ceilings, not usage or cost. `tests/fault-investigations.spec.ts` covers the flow, including keyboard consent and 390px layout.

## Remote execution

Experiments can run on finite remote workers while SQLite stays with one coordinator:

Deployment contexts, the coordinator and workers use one pinned Linux runtime: Python 3.11.9 with the versions in `docker/runtime-constraints.txt`. Loading a context reruns its recorded evaluation, so the coordinator runs in the same image as the context it loads:

```powershell
docker build -f docker/worker.Dockerfile -t sidekick-worker .
docker run --rm --entrypoint python -v ${PWD}/output:/out sidekick-worker scripts/evaluate_fault_scenarios.py --profile synthetic-rotating-v1 --output /out/context-package
docker run --rm --entrypoint python -v ${PWD}/output:/out -v ${PWD}/jobs:/jobs sidekick-worker scripts/run_fault_investigation.py --store /out/investigations --context /out/context-package --trust-local-artifact --run <id> --remote-outbox /jobs/outbox --remote-inbox /jobs/inbox --allow-transfer
docker run --rm -v ${PWD}/jobs:/jobs -v ${PWD}/output/context-package:/context:ro sidekick-worker --manifest /jobs/outbox/<job>.json --context /context --inbox /jobs/inbox --trust-local-artifact
```

For each case, the coordinator writes a job manifest with:

- a job ID
- the context fingerprint and the checksums of the context package files
- the policy fingerprint and the source digest (it hashes `backend/app` with line endings normalized, so a Windows checkout and a Linux worker built from the same commit agree)
- the case and its time limit

The worker checks every one of these, evaluates exactly one case under kernel CPU and memory limits (`--cpu-seconds`, `--memory-mb`), writes one result artifact atomically, and exits. Native scoring calls are stopped by those limits even when cooperative cancellation cannot reach them.

The coordinator accepts only a result whose job ID and manifest digest match the job it issued and whose evaluation checksum, case, context and policy all agree. The runner then applies its normal lease and identity checks.

- Duplicate deliveries are expected and ignored after the first match. Forged or stale results are never read as valid.
- A failed or timed-out job is retried with a new job ID up to three times, then recorded as one failed attempt.
- A result that arrives after cancellation is never published.
- A remote result matches local execution only when both run in the same numerical runtime. Package versions are not enough: Windows and Linux fits differ in the last bits, so a worker refuses a context made on another platform when its recorded evaluation does not reproduce.

Context packages contain raw development data, so remote execution needs `--allow-transfer`, and local execution remains the default. The outbox and inbox can be shared folders or a synced object store. Workers never touch the SQLite file. GPUs and serverless endpoints are unnecessary for these small tabular models; measure a real workload before adding them.

## Fault research

Each completed finding has **Research this fault**. Review the generic fault-type search, then explicitly allow one Tavily search and one Nemotron request. Workspace AI permission must also be enabled. Set `TAVILY_API_KEY` alongside the existing `NEBIUS_API_KEY` in the local `.env`, then restart Sidekick. Keep keys on the server.

Tavily receives only the displayed query. Results without sensor or measurement terminology in their title or saved excerpt are excluded; this simple filter does not establish relevance or authority. Nemotron receives up to three bounded source excerpts and aliased aggregate results, with at most 1024 output tokens plus 4096 reasoning tokens. Sources are untrusted context; citation IDs must match the returned sources. Research never changes the finding, criterion, policy or model and does not load a fitted context.

The initial live check made one successful Tavily request (one reported credit) and one Nemotron request (265 reported completion tokens). Tavily returned unrelated Microsoft pages; Nemotron declined to infer sensor-specific tests. The sources are now rejected by the technical-term filter in an offline replay. Live retrieval of useful engineering references remains unverified.

One research attempt is saved per experiment, including failures, cancellations and interruptions. Reopening or submitting another request reuses it without paid retries. Revocation and cancellation are checked before each provider stage and before publishing advice. Running requests stop at the next safe checkpoint. Research appears in the private investigation export; the public measured-evidence export excludes it. Hosted recorded investigations remain read-only.

## Public evidence

`--public-export <id> file.json`, `GET /api/investigations/{id}/public-export` and the workbench's **Public evidence** button all write the same file. It is separate from the private replay package and contains:

- the context, configuration and policy fingerprints, fixed thresholds, bounds and profile constraints with their provenance
- the finding criterion, budget use, and proposal, rejection and duplicate counts
- every tested case's parameters, finding status, coverage, clean and faulted metrics, effect counts and the assumptions it relies on
- discovery families
- who chose each case (`nemotron` or `supplied`)
- the controller's model, prompt version, reasoning effort, call count, reserved and reported tokens, and for each Nemotron proposal the results it cited and whether its fault family was new
- reduction steps and claims, remedy comparisons with costs and unresolved failures, and validations on fresh histories
- a `demonstration` note when a setting, such as a deliberately fragile threshold, was chosen for illustration
- reproduction steps when the profile is synthetic

It leaves out the objective, equipment IDs, per-history support, raw readings, fitted objects, keys and request IDs. A SHA-256 digest of the content shows the file is unchanged; it does not show who made it or that it may be shared. Non-synthetic contexts are marked as not publicly replayable.

Recorded public evidence lives in `evidence/` and is shown read-only on the hosted site:

- `investigations/synthetic-recorded.json`: the default synthetic package at automatically selected thresholds, three seed cases and three compound cases; no provider calls. An honest null result that shows the format.
- `investigations/nemotron-live-default.json`: a bounded live Nemotron run on the same default context.
- `investigations/nemotron-live-demo.json`: the full story at the demonstration threshold, with Nemotron's cases marked, reduction, remedy and validation on fresh histories.
- `investigations/nemotron-live-browser.json`: a bounded Nemotron search started from the browser workbench, including Nemotron's own measured failure, its reduction, remedy and fresh validation.
- `regressions/`: the reduced regression cases from both stories.
- `benchmarks/`: the synthetic-fixture comparison and the recorded Nemotron comparison.

Each was made from one commit, replayed exactly, and exported with the steps above. The private stores, context packages and sanitized live captures stay with the person who ran them.
