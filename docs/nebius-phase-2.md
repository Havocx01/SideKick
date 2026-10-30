# Compound-fault evaluator: Phase 2

Phase 2 adds a developer-facing engine for reproducible sensor-measurement corruption. It reuses fitted development-fold models and training-only preprocessing, with fixed thresholds. Existing browser protocols and the recorded benchmark remain single-sensor. Adaptive experiment selection and finding criteria are covered in [the investigation guide](nebius-phase-3.md).

## Run the isolated synthetic example

From the repository root, after installing the normal training dependencies:

```powershell
.venv\Scripts\python.exe scripts/evaluate_fault_scenarios.py --output output/phase-2-example
.venv\Scripts\python.exe scripts/evaluate_fault_scenarios.py --replay output/phase-2-example --trust-local-artifact
```

The first command creates a new directory, generates 26 synthetic equipment histories, reserves four without scoring them, fits two development folds once, chooses thresholds on clean out-of-fold predictions, and evaluates a dropout plus drift on different sensors. It exports the fitted context, scenario, evaluation and checksum manifest. The second command checks provenance/integrity and reproduces the evaluation without fitting. Both commands make zero provider requests and use no saved application workspace.

Choose a new output directory each time; existing runs are never overwritten. `--scenario path/to/scenario.json` can supply a custom bounded case for the synthetic fixture. The JSON shape is:

```json
{
  "version": 1,
  "components": [
    {"sensor": "temp_bearing", "kind": "dropout", "duration": "persistent", "onset_before_failure": 40},
    {"sensor": "vibration_rms", "kind": "drift", "duration": "persistent", "onset_before_failure": 40,
      "severity_sd": 1.5, "sign": 1, "ramp_cycles": 10}
  ]
}
```

## Use the engine with an existing development fit

Given a trusted `TrainingResult` returned by `train_development` and thresholds already chosen from its clean development predictions:

```python
from app.faults.evaluator import FixedDevelopmentEvaluator
from app.faults.scenarios import FaultCase, FaultPolicy

policy = FaultPolicy(
    allowed_sensors=("temp_bearing", "vibration_rms"),
    max_components=2,
    assumptions="Prototype measurement-corruption bounds; not equipment-validated."
)
engine = FixedDevelopmentEvaluator(training, fixed_thresholds, policy)
case = FaultCase.model_validate(scenario_json)
result = engine.evaluate(case)
```

The engine validates complete/disjoint fold membership and development-only data before scoring, takes its own snapshot, and never calls `fit`. Changing the caller's source data or threshold dictionary does not alter the fixed context. Constructor preparation scores clean histories once. Every new scenario reuses the fitted models, clean scores, preprocessing and alert rules.

## Scenario semantics

- Each component affects a different sensor. Same-sensor composition is rejected, even with disjoint intervals; no hidden precedence is assumed.
- Components use independent copies of the same clean inputs. A history is eligible only when every component can apply and changes scorable features. Incomplete compound cases are excluded atomically, not scored as smaller cases.
- Explicit onsets use cycles before failure for retrospective stress testing. Random onsets require an explicit seed, including seed zero. Neither is a deployable predictor of future failure time.
- Drift magnitude uses each fold's training standard deviation. Faults do not alter labels, fitted preprocessing, models or thresholds.
- New scenario IDs hash full-precision canonical parameters and ignore component ordering. Legacy single-fault IDs and behavior are unchanged.
- The default policy allows two components, drift up to three training SD, ramp/transient length up to 120 cycles and explicit onset up to 500 cycles before failure. Allowed sensor groups can narrow combinations. These are declared prototype assumptions, not evidence of physically consistent equipment failures.

## Read the result

`complete` means all expected development histories were scored; `partial` lists exclusions; `not_applicable` has no faulted or matched-clean metrics. It never treats lack of coverage as successful robustness or as a model failure.

Each model includes clean metrics on all development histories, clean/faulted metrics on the same eligible histories, descriptive fault-minus-clean deltas, per-history outcomes and exact prediction digests. Applied onset indices and affected-cycle counts are recorded per component. Thresholds, configuration, source, policy and fitted-context identities accompany the result. These results do not establish factory benefit, causal physical diagnosis or deployment readiness.

Budgets limit context rows/histories, model/fold counts and new scenario evaluations. Identical cases reuse a defensive copy of cached evidence. Failed executions consume an evaluation slot; a pre-start cancellation does not. Time limits and cancellation are cooperative between bounded work units, not a hard interrupt of a native estimator call. A future public agent runtime still needs process isolation and durable scheduling.

## Local replay boundary

`context.joblib` contains fitted Python objects and **raw development data and identifiers**. Keep real-data packages local unless disclosure is authorized. This is not the public submission export format. No reserved history rows are included.

Only load a package you created and trust. `--trust-local-artifact` is required because Python/joblib deserialization can execute code. Checksums detect accidental modification; they do not authenticate a malicious package. Replay requires the same source and dependency versions, checks file sizes/checksums before loading, and compares the complete recomputed result. It makes no changes to the original package or application exposure ledger.
