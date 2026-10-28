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

The controller holds the runner lease while the model thinks. Cancellation and the saved run-time deadline also apply while awaiting a provider response. Another runner cannot execute the same investigation concurrently, and a lost lease cannot publish a reply. Local validation failures can lead to a new proposal within the remaining limits; malformed responses and provider errors stop the invocation. Changing the saved model, endpoint, prompt or limits requires a new investigation. Rotating a key does not reset counters.

`--status <id>` shows controller configuration, reservations and call outcomes without a key or model context. The final controller report includes cumulative calls/experiments used and result references. A model stop is not evidence that all failure modes were tested. Scenario reduction, remedy testing, search baselines and a browser interface remain separate work.
