# Nebius Investigator: Phase 1

Status: DONE. Planned assurance: Standard. Effective assurance: Standard.
One owner; provider transport, configuration, consent and evidence verification are the affected seams.
Arc's supporting reference bundle is not installed. Use the existing repository's scoped local implementation approach with independent read-only spec and code review.

## Implementation state

- Baseline: `5dcb9b4854d06a0158ac6c2f8df26ee36dbf0633`.
- Branch: `feat/nebius-investigator`, created from the clean current Sidekick checkpoint.
- Pre-existing dirty paths: none.
- Commit posture: leave changes uncommitted; no push, deployment or submission.
- Baseline verification: 110 focused backend tests passed (provider, deep investigation, workspace consent, routine analysis).
- Nebius credential availability: absent in the process and repository `.env`; no credential values were printed.

## Scope and acceptance

1. Add explicit provider/key/endpoint configuration with backward-compatible OpenAI defaults.
2. Add a Nebius Chat Completions adapter for structured responses and read-only tool calls; retain server validation, request ceilings and no retries.
3. Route deep investigation and internal legacy investigation through the adapter. Keep routine analysis local and saved reports readable.
4. Make availability, sanitized errors, consent disclosures and output identities provider-aware. Require explicit consent for a newly selected Nebius endpoint.
5. Add an opt-in, two-request synthetic smoke check and configuration/setup documentation. Default checking must make no network requests.
6. Verify transport and lifecycle with real SDK serialization against an offline HTTP transport, plus affected regressions and repository checks.

Declared paths: `backend/app/config.py`, `backend/app/assistant/transport.py`, `backend/app/assistant/agent.py`, `backend/app/assistant/deep.py`, `backend/app/assistant/service.py`, `backend/app/assistant/store.py`, `backend/app/api/routes_assistant.py`, `backend/app/experiments/jobs.py`, `.env.example`, `README.md`, `scripts/check_nebius.py`, `tests/test_nebius_provider.py`, `tests/test_worker_lifecycle.py`, `tests/test_deep_matrix.py`, `docs/nebius-phase-1.md`. Plan/index metadata is excluded from implementation evidence.

Out of scope: compound faults, adaptive experiment execution, changes to model training or reserved evaluation, user-workspace jobs, cloud deployment, public licensing decisions for shared code, and application submission. Preserve saved artifacts and the local `.env`. Integration checks may train synthetic fixtures in isolated test-owned workspaces.

## Verification commands

- `.venv/Scripts/python.exe -m pytest -q tests/test_nebius_provider.py`
- `.venv/Scripts/python.exe -m pytest -q`
- `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`
- `.venv/Scripts/python.exe scripts/check_nebius.py`
- `.venv/Scripts/python.exe scripts/generate_types.py --output output/nebius-phase-1-types.ts` (compare bytes with committed frontend types)
- Frontend `npm run lint`, `npm run typecheck`, `npm run test:protocol`, `npm run build`; targeted consent/deep browser checks as appropriate.
- `git diff --check`

Live model compatibility remains unverified until a Nebius key is configured and the explicit smoke check succeeds. Mocked transport success is not evidence of live model behavior or hackathon readiness.

## Closeout: passed (27 October 2026)

Attributable target fingerprint (SHA-256 of sorted `path:file-sha256` pairs, joined by newlines):
`f54b16e238e63decb1b0fee334e4b835ad7fabe0b6c542b22192f067ec1612a3`.
Fifteen implementation files; plan/index metadata excluded. Starting HEAD remains unchanged.

- Final full backend gate: **465 passed, 1 skipped**, 180.45 seconds. The existing two test-library deprecation warnings remain.
- New provider coverage: **26 tests**; real SDK serialization uses offline HTTP transport. Covers strict schema, truncation/refusal/invalid output, tool transcript conversion, selected credentials, endpoint validation, current deep lifecycle, local-only routine analysis, endpoint approval, reciprocal provider switching, retained report access, revocation, identities, and offline/live probe admission.
- Browser gate: **28 passed** across `workspace-ai-permission.spec.ts` and `deep-investigation.spec.ts` (mobile/desktop, both themes, mocked AI).
- Final Ruff, frontend lint, TypeScript, **7 protocol tests**, generated API type byte comparison, production build, offline smoke checker and `git diff --check`: passed.
- Existing frontend chunk-size advisory remains. No frontend source or public API schema changed.
- Independent spec and code/security reviews approved the final implementation. First review found cross-provider approval and retained-output access issues; both were fixed and covered by regression tests before the fresh full gate.
- One offline matrix fixture now supplies an explicit mock credential, matching the new missing-key preflight. No real provider call is made by that fixture.

Exact final commands: `.venv/Scripts/python.exe -m pytest -q --tb=short`; `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`; `.venv/Scripts/python.exe scripts/check_nebius.py`; `.venv/Scripts/python.exe scripts/generate_types.py --output output/nebius-phase-1-types.ts` followed by byte comparison; frontend `npm run lint`, `npm run typecheck`, `npm run test:protocol`, `npm run build`; `git diff --check`. Browser command: `npm test -- workspace-ai-permission.spec.ts deep-investigation.spec.ts`, with `SIDEKICK_TEST_PYTHON` set to the repository virtual environment.

Zero live/paid provider requests. No user `.env`, saved evidence or workspace stores were edited; no deployment or submission. Live Nebius verification is credential-blocked, not passed. All Phase 1 implementation changes remain **uncommitted** on `feat/nebius-investigator`; they exist in the working tree and must be preserved before any reset.

Next phase: combined-fault scenario schema/injection/scoring and a reusable bounded evaluator, before adaptive experiment execution.
