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

Setup, validation, status and ordinary runner actions stay local. Only the explicit controller action makes provider requests. This developer interface has no HTTP route; existing workspace, consent and exposure databases are separate.

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

### Search context

Each request starts from clean performance: every fixed model's detection and alarm burden on all development histories. Each completed experiment gets a stable `result-N` ref, its family (sensor and fault-kind combination, ignoring timing and severity) and, when a criterion is saved, its finding status. A family table (up to 24, with an omitted count) gives experiments, measured failures and the worst detection change for every family tested so far. The rejected-proposal count and the last three validator reasons are included. Full detail is kept for the latest twelve cases, so the input stays bounded however long the run.

A proposal may include a hypothesis: what is suspected, what measurement would support it, what would weaken it, and the `result-N` refs it builds on. Refs are mapped to real attempt IDs before saving; an unknown ref rejects the proposal. Hypotheses are stored as unverified model text, separate from measured results. `--findings` reports `discoveryFamilies`, so many severities of one combination count as one discovery.

`--create … --seed N` prepends up to N deterministic single-channel cases, choosing one channel from each declared group first, so the first measurements span the profile before the model chooses.

### Live smoke run

From the repository root on Windows, with `NEBIUS_API_KEY` and `SIDEKICK_ASSISTANT_PROVIDER=nebius` in `.env`:

```powershell
.venv\Scripts\python.exe scripts/check_nebius.py --live
.venv\Scripts\python.exe scripts/evaluate_fault_scenarios.py --output output/live-context
'[]' | Out-File -Encoding ascii output/empty.json
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --context output/live-context --trust-local-artifact --create output/empty.json --objective "Find sensor faults that cost useful warnings."
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --context output/live-context --trust-local-artifact --agent <id> --allow-nebius --max-provider-calls 2 --max-completion-tokens 10240 --capture output/live-capture.json
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/live-store --status <id>
```

The run uses synthetic data only and makes at most two billable calls. It is complete when a Nemotron proposal is validated, evaluated and saved, and the status read shows it. A failed call is still captured; it is evidence, not a completed end-to-end test.

The controller holds the runner lease while the model thinks. Cancellation and the saved run-time deadline also apply while awaiting a provider response. Another runner cannot execute the same investigation concurrently, and a lost lease cannot publish a reply. Local validation failures can lead to a new proposal within the remaining limits; malformed responses and provider errors stop the invocation. Changing the saved model, endpoint, prompt or limits requires a new investigation. Rotating a key does not reset counters.

`--status <id>` shows controller configuration, reservations and call outcomes without a key or model context. The final controller report includes cumulative calls/experiments used and result references. A model stop is not evidence that all failure modes were tested. Scenario reduction, remedy testing, search baselines and a browser interface remain separate work.

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

`--regression <reduction-id> file.json` exports the final case with its criterion, expected status, context and policy fingerprints, profile and source IDs. `checkRegression` reruns it and refuses a different fitted context or policy.

## Remedies

`--remedy <id> threshold --threshold 0.5` or `--remedy <id> augmented --approve-training` compares a remedy against the original fixed context. Remedies:

- `threshold` reuses the same fitted models with an explicitly chosen warning threshold for the target model. It is an explicit candidate change, so it has its own context fingerprint.
- `augmented` retrains the same development folds with sampled sensor-fault augmentation and selects its threshold on clean out-of-fold predictions. Training needs `--approve-training` and never reads reserved histories.

The comparison reruns every discovered case, every finished reduction, any regression files (`--regressions a.json b.json`, which must match the context and policy) and every other tested case. For each case it reports the original and remedy finding status, evaluated histories, exclusions, clean and faulted detection and burden, faulted median lead, and whether the matched cohort is the same. `improved` counts failures that became `no_measured_failure` on the same cohort. `degraded` counts previously passing cases that now fail. Clean performance on all development histories is shown for both. `meetsCriteria` means the remedy's clean detection and burden satisfy the saved criterion and nothing degraded. Preparation and evaluation time are recorded as cost.

Reports are saved in the store. They are development-only and were chosen using these cases, so a promising remedy needs fresh validation. Nothing replaces a deployed model.

## Search benchmark

`scripts/benchmark_search.py --output report.json` compares search strategies on the synthetic fixture. Every strategy gets:

- a fresh evaluator for each run, so no strategy reuses another's cache
- the same profile and the same finding criterion
- the same three seed cases, which count toward the budget
- the same experiment budget (`--budget`, default 24)

Each strategy runs once per context (`--thresholds`) and seed (`--seeds`). Strategies:

- `fixed`: every permitted single-channel fault at the warning horizon, in order.
- `random`: constrained random sampling within the profile's groups, kinds, severity caps and onsets.
- `climb`: (1+1) hill climbing on a discrete encoding. It changes one onset, one severity or one kind, or adds or drops one channel in the same group, around the case with the largest detection drop, never repeats a tested case, and restarts at random one time in five.
- `recorded` (`--recorded cases.json --provider-calls N`): the cases a Nemotron run proposed, replayed under the same budget.

Infeasible proposals, duplicates and failed executions are counted. Each run reports discoveries, discovery families (the dedup rule is stated in the report), experiments to the first discovery, the strongest detection drop, the most lost warnings, mean coverage, families tested, feasibility rate, elapsed time and provider calls. Results are out-of-fold development evidence; findings chosen adaptively are exploratory.

A first run (budget 24, five seeds, thresholds 0.95 and 0.9) found 3 discovery families with `random` in 2 of 10 runs, and none with `fixed` or `climb`. The climber has no signal to follow when early cases change nothing, so random sampling did better here. That is the result to report. A Nemotron comparison needs a recorded live run.

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

```powershell
.venv\Scripts\python.exe scripts/run_fault_investigation.py --store output/investigations --context output/context-package --trust-local-artifact --run <id> --remote-outbox jobs/outbox --remote-inbox jobs/inbox --allow-transfer
docker build -f docker/worker.Dockerfile -t sidekick-worker .
docker run --rm -v ${PWD}/jobs:/jobs -v ${PWD}/output/context-package:/context:ro sidekick-worker --manifest /jobs/outbox/<job>.json --context /context --inbox /jobs/inbox --trust-local-artifact
```

For each case, the coordinator writes a job manifest with:

- a job ID
- the context fingerprint and the checksums of the context package files
- the policy fingerprint and the source digest
- the case and its time limit

The worker checks every one of these, evaluates exactly one case under kernel CPU and memory limits (`--cpu-seconds`, `--memory-mb`), writes one result artifact atomically, and exits. Native scoring calls are stopped by those limits even when cooperative cancellation cannot reach them.

The coordinator accepts only a result whose job ID and manifest digest match the job it issued and whose evaluation checksum, case, context and policy all agree. The runner then applies its normal lease and identity checks.

- Duplicate deliveries are expected and ignored after the first match. Forged or stale results are never read as valid.
- A failed or timed-out job is retried with a new job ID up to three times, then recorded as one failed attempt.
- A result that arrives after cancellation is never published.
- Remote results are identical to local execution, because the evaluation is deterministic.

Context packages contain raw development data, so remote execution needs `--allow-transfer`, and local execution remains the default. The outbox and inbox can be shared folders or a synced object store. Workers never touch the SQLite file. GPUs and serverless endpoints are unnecessary for these small tabular models; measure a real workload before adding them.
