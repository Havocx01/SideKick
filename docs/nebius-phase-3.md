# Investigation records

Investigation setup is saved locally. Typed scenario proposals can be validated against that setup; automatic selection and experiment execution are not connected yet.

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

The experiment cap cannot exceed the evaluator policy. Budget consumption, elapsed-time accounting and lifecycle transitions will be added with the runner. `check_context` rejects a different evaluator; the caller must supply the original fitted context. The record alone cannot reconstruct it.

This developer interface has no HTTP route and makes no provider requests. Existing workspace, consent and exposure databases are separate.

## Scenario proposals

`ScenarioProposal` contains a `scenario` using the existing `FaultCase` contract and a short `reason`. It can be used as the existing provider adapter's response model. The reason is unverified model text, not measured evidence or an instruction to execute.

```python
from app.investigator.proposals import validateProposal

proposal = validateProposal(responseJson, loaded, evaluator)
scenarioId = proposal.scenario.scenario_id
```

Validation accepts JSON text up to 16 KiB. It rejects extra fields, incorrect types, empty reasons, invalid fault parameters, unknown sensors and violations of the investigation's component/group/timing/severity bounds. The record is revalidated and must match the evaluator's fixed context. Scenario IDs are computed locally from canonical parameters.

This check does not determine whether a fault changes scorable readings; the evaluator reports actual applicability and coverage. Validation neither saves proposals nor consumes budget. The future runner must reload the record and validate each proposal before execution and account for duplicates, failed proposals and experiment limits.
