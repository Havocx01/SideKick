# Sidekick

**Selects failure-prediction models by how their alerts survive sensor faults.**

ABB Accelerator 2026, Theme 1 — Agentic Predictive Maintenance Studio.
Adam Qablawi and Kareem Massoud.

---

## The problem

A predictive-maintenance model is chosen on clean historical data and then deployed
onto sensors that drop out, freeze, and drift. Nothing in the usual selection
process asks what happens then, so the question is answered in production, by the
alert that never arrived.

## What this does

Sidekick trains a set of candidate models, then re-scores every one of them under a
matrix of injected sensor faults, and recommends the model whose **warnings hold
up** rather than the one with the best clean-data score. The full result on NASA
C-MAPSS FD001 is committed to this repository and served by the hosted demo.

### The result this produces

Six of the ten candidates reach **100% detection on clean data**. On clean data they
are indistinguishable, and any of them would look like a defensible choice.

Under the required fault set, they separate by up to 49 percentage points:

| Candidate | Clean | Worst required fault | Qualifies |
|---|---:|---:|---|
| `xgboost_augmented/aug3` *(recommended)* | 100% | **99%** | yes |
| `xgboost/xgb1` | 100% | 99% | yes |
| `xgboost_augmented/aug1` | 100% | 93% | yes |
| `xgboost/xgb2` | 100% | 81% | yes |
| `age_baseline/age1` *(reads no sensor)* | 70% | 70% | yes |
| `logistic_regression/lr3` | 100% | 68% | **no** |
| `logistic_regression/lr1` | 100% | 68% | **no** |
| `logistic_regression/lr2` | 100% | **51%** | **no** |

Three candidates with perfect clean-data detection are disqualified. `lr2` loses
half its detections when one sensor stops reporting 60 cycles before failure.

The recommended model was then scored **once** on 20 engines that no model,
threshold, or selection decision had ever seen: 100% detection clean, 100% under
its worst required fault, 95% interval 0.84–1.00. The interval is wide because 20
engines is 20 engines, and the interface says so rather than reporting the point
estimate alone.

## What it does not establish

Stated here, in the interface, and in the evidence bundle, because a limitation
that only appears in a report does not travel with the number:

- One dataset, one failure mode, simulated. C-MAPSS is a simulation, not a fleet.
- Faults are injected synthetically. Real sensor failures are messier and correlate
  with the conditions that cause the failure being predicted.
- 100 engines total. Intervals are wide and small differences between candidates
  are not established by the data — the ranking flags the pairs it cannot separate.
- Feature attributions describe model behaviour, not physical cause.

---

## Quick start

```bash
git clone <this repo> && cd Project-ABB

# Windows                         # macOS / Linux
.\tasks.ps1 setup                 make setup
.\tasks.ps1 data                  make data        # downloads C-MAPSS FD001
.\tasks.ps1 pipeline              make pipeline    # ~3 min, writes evidence/bundle.json
.\tasks.ps1 build                 make build
.\tasks.ps1 api                   make api         # http://127.0.0.1:8000
```

The evaluation is already committed at `evidence/bundle.json`, so `api` alone is
enough to browse the recorded result. Run `make help` or `.\tasks.ps1 help` for
every task.

With Docker:

```bash
docker compose up          # API on :8000, frontend with hot reload on :5173
docker build -t sidekick . && docker run -p 8000:8000 sidekick   # the deployed image
```

## The three views

1. **Data setup** — what the data is, what the profiler found wrong with it, how it
   is partitioned, and what counts as a useful warning. All fixed before any model
   is trained.
2. **Model comparison** — candidates ranked by worst-case detection under fault,
   with confidence intervals, a per-sensor fault heatmap, and calibration.
3. **Warning replay** — one machine's history cycle by cycle, clean and faulted on
   one axis, with the alert episodes and what moved the score.

A copilot panel answers questions about the recorded evaluation. It reaches the
results through a fixed set of tools, and every figure in an answer is checked
against the tool output that should contain it; unverified figures are labelled as
such. Without an API key it still answers, deterministically, from the evidence.

## How the result stays trustworthy

| Risk | What the code does |
|---|---|
| Leakage between train and test | Partitioned by equipment, never by row. Preprocessing statistics are fit on training engines only. Enforced by `assert_engine_disjoint` and tested. |
| Features that see the future | Windows are strictly trailing. `assert_no_lookahead` verifies that changing a future reading cannot change a past feature. |
| Thresholds tuned to the test | Thresholds are chosen on clean out-of-fold scores, before the fault matrix runs. |
| Selecting on the holdout | The holdout is scored once, on the candidate development already chose. `score_holdout.py` refuses to run if no candidate was recommended. |
| A tool that always finds a winner | "No candidate qualifies" is a valid outcome the selection rule can return. |
| Numbers that move between runs | `check_reproducibility.py` runs the evaluation twice and compares every metric: 1359 metrics, maximum difference 0. |
| A copilot inventing figures | Numeric claims are matched against recorded tool output before the answer is shown. |

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit, and why the hosted demo is read-only.
- [Metrics](docs/metrics.md) — exactly what detection, burden, and lead time mean here.
- [Decisions](docs/decisions.md) — the choices that shaped the result, and what was rejected.
- [Development](docs/development.md) — setup, tasks, testing, and deployment.

## Layout

```
backend/app/
  config.py      Frozen experiment definition; changing it changes the fingerprint
  schemas.py     One contract, shared by the pipeline, the API, and the frontend
  data/          Loading, the upload contract, profiling, synthetic fallback
  features/      Causal windowed features with a single-sensor rebuild path
  models/        Splits, candidates, cross-validated training, thresholds
  faults/        Fault specification, injection, and the scenario matrix
  scoring/       Alert episodes, operational measures, the selection rule
  evidence/      Run records, optional MLflow mirror, the replay bundle
  copilot/       Tool registry, numeric-claim verification, bounded agent loop
  api/           FastAPI surface
frontend/src/    React views, charts, and the copilot panel
scripts/         fetch_data, run_pipeline, score_holdout, check_reproducibility,
                 export_bundle, generate_types
evidence/        bundle.json — the committed evaluation the demo serves
```

## Idea-phase proposal

[PDF](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.pdf) ·
[Word](Idea%20Phase/documents/Sidekick%20ABB%20Accelerator%202026%20Final%20Submission.docx)
