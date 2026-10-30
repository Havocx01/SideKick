# Testing

Install development dependencies, then run from the repository root:

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/generate_types.py --output output/generated-types-check.ts
```

Compare `output/generated-types-check.ts` with `frontend/src/api/types.ts`. To update the checked-in contract intentionally, run `scripts/generate_types.py` without `--output`.

```powershell
$env:SIDEKICK_TEST_PYTHON = (Resolve-Path '.venv/Scripts/python.exe').Path
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm run test:protocol
npm run build
npx playwright install chromium
npm test
```

Build before starting browser tests and leave the built files unchanged until they finish. Browser tests use isolated workspaces. On Linux, use the virtual environment's `bin/python` and `npx playwright install --with-deps chromium`.

## Coverage

- Data mapping, complete-history validation, grouped splits and reserved-history separation.
- Training, fault injection, matched metrics, freezing and one-time reserved evaluation.
- Local compound-fault evaluation, deterministic replay and investigation-record persistence.
- Provider transport, permission checks, cancellation, saved reports and review-brief recovery.
- Browser navigation, library actions, CSV failures, themes, mobile layout and exports.

Finding-count and acceptance-boundary tests use explicit warning traces; learned-model integration tests check findings against their recorded matched outcomes. Remedy fixtures test both a successful threshold change and a change that increases alarm burden. Exact learned-model counts are specific to the fitted context and are not portable reference values.

Routine checks mock cloud calls. Keep `SIDEKICK_ASSISTANT_LIVE_ENABLED=0` and `SIDEKICK_ASSISTANT_LIVE_EVAL=0` in CI. Explicit live switches in evaluation scripts incur provider charges and do not belong in normal tests. Recorded captures are historical evidence; fixture success does not establish current model quality or engineer benefit.

The recorded `evidence/bundle.json` must retain its exact bytes. `.gitattributes` disables line-ending conversion because replay compatibility checks its SHA-256. `tests/test_evidence_checkout.py` covers checkout/archive compatibility and checksum rejection.

## Focused checks

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_investigation_records.py tests/test_scenario_proposals.py tests/test_compound_faults.py tests/test_fault_investigation.py
.venv\Scripts\python.exe -m pytest -q tests/test_nebius_provider.py tests/test_deep_investigation.py
.venv\Scripts\python.exe -m pytest -q tests/test_nemotron_controller.py tests/test_fault_investigation.py
.venv\Scripts\python.exe -m pytest -q tests/test_investigation_findings.py tests/test_fault_profiles.py tests/test_adaptive_search.py tests/test_reduction.py tests/test_remedies.py
.venv\Scripts\python.exe -m pytest -q tests/test_search_benchmark.py tests/test_investigations_api.py tests/test_remote_jobs.py tests/test_public_export.py tests/test_failure_injection.py
.venv\Scripts\python.exe -m pytest -q tests/test_fault_research.py
.venv\Scripts\python.exe scripts/evaluate_deep.py --output output/deep-review-new
```

`tests/test_failure_injection.py` runs one investigation through provider truncation, malformed and unknown-alias replies, network errors, lease loss and a process crash, and checks that earlier evidence, its finding and paid-call counters never change or reset. The investigation workbench browser tests are in `frontend/tests/fault-investigations.spec.ts`.

The offline deep review needs a new output directory to preserve previous results and reviewer notes. See the [Nebius setup](docs/nebius-phase-1.md), [compound evaluation guide](docs/nebius-phase-2.md) and [engineer evaluation guide](docs/sidekick-engineer-evaluation.md) for those workflows.

## Docker and CI

```powershell
node scripts/check_local_docker.mjs
docker build --target demo -t sidekick-memory .
docker run -d --name sidekick-memory --memory=512m --memory-swap=512m sidekick-memory
docker cp scripts/check_hosted_memory.py sidekick-memory:/tmp/check_hosted_memory.py
docker exec sidekick-memory python /tmp/check_hosted_memory.py
docker build -f docker/worker.Dockerfile -t sidekick-worker .
.venv\Scripts\python.exe scripts/check_worker_image.py
```

Deployment contexts, workers and the hosted app share one pinned Linux runtime: Python 3.11.9 and the exact versions in `docker/runtime-constraints.txt`. Matching versions alone is not enough; native Windows and Linux fits differ in the last bits, so strict replay refuses a context made on another platform. Create deployment context packages inside the worker image. `check_worker_image.py` prepares evidence in one container and checks a separate worker container from the same image; both run without network access. Its `--command` option checks local execution instead. The synthetic generator uses only exact arithmetic, so its data is identical on Windows and Linux.

The GitHub workflow runs backend, generated-contract, frontend, browser, worker-image and hosted-memory checks, all offline; paid provider checks only run through `check_nebius.py --live` or an explicit `--agent --allow-nebius` command. It does not deploy. Failed browser traces and reports are retained for seven days in the `browser-failure-diagnostics` artifact; inspect traces with `npx playwright show-trace <trace.zip>`.

Automated checks establish software behavior on fixtures and synthetic data. Real-equipment reliability, deployment suitability and measured engineer usefulness require separate evaluation.
