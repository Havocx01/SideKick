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

Routine checks mock cloud calls. Keep `SIDEKICK_ASSISTANT_LIVE_ENABLED=0` and `SIDEKICK_ASSISTANT_LIVE_EVAL=0` in CI. Explicit live switches in evaluation scripts incur provider charges and do not belong in normal tests. Recorded captures are historical evidence; fixture success does not establish current model quality or engineer benefit.

The recorded `evidence/bundle.json` must retain its exact bytes. `.gitattributes` disables line-ending conversion because replay compatibility checks its SHA-256. `tests/test_evidence_checkout.py` covers checkout/archive compatibility and checksum rejection.

## Focused checks

```powershell
.venv\Scripts\python.exe -m pytest -q tests/test_investigation_records.py tests/test_scenario_proposals.py tests/test_compound_faults.py
.venv\Scripts\python.exe -m pytest -q tests/test_nebius_provider.py tests/test_deep_investigation.py
.venv\Scripts\python.exe scripts/evaluate_deep.py --output output/deep-review-new
```

The offline deep review needs a new output directory to preserve previous results and reviewer notes. See the [Nebius setup](docs/nebius-phase-1.md), [compound evaluation guide](docs/nebius-phase-2.md) and [engineer evaluation guide](docs/sidekick-engineer-evaluation.md) for those workflows.

## Docker and CI

```powershell
node scripts/check_local_docker.mjs
docker build --target demo -t sidekick-memory .
docker run -d --name sidekick-memory --memory=512m --memory-swap=512m sidekick-memory
docker cp scripts/check_hosted_memory.py sidekick-memory:/tmp/check_hosted_memory.py
docker exec sidekick-memory python /tmp/check_hosted_memory.py
```

The GitHub workflow runs backend, generated-contract, frontend, browser and hosted-memory checks. It does not deploy. Failed browser traces and reports are retained for seven days in the `browser-failure-diagnostics` artifact; inspect traces with `npx playwright show-trace <trace.zip>`.

Automated checks establish software behavior on fixtures and synthetic data. Real-equipment reliability, deployment suitability and measured engineer usefulness require separate evaluation.
