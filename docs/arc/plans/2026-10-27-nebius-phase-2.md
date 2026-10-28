# Nebius Investigator: Phase 2

Status: DONE. Planned assurance: Guarded. Effective assurance: Guarded.
Reason: new evaluation code must preserve grouped development scoring, matched coverage, fitted-model identity and reserved-data separation.
Use the installed implement skill's locally supported workflow; supporting Arc reference files remain unavailable. One implementation owner, independent spec/code/data review before closeout.

## Implementation state

- Baseline: `4c956f0fa919b66398c7f2f4351d90cf2b858c14`.
- Branch: `feat/nebius-investigator`; starting worktree clean.
- Phase 1 is now committed/pushed at this baseline; its old uncommitted closeout describes the earlier session only.
- Commit posture: leave Phase 2 changes uncommitted; no push, deployment or submission.
- Baseline focused check: 6 protocol/metrics/paired-comparison tests passed.
- Declared implementation paths: `backend/app/faults/scenarios.py`, `backend/app/faults/evaluator.py`, `backend/app/faults/replay.py`, `scripts/evaluate_fault_scenarios.py`, `tests/test_compound_faults.py`, `docs/nebius-phase-2.md`, `README.md`.
- Plan/index metadata excluded from implementation fingerprints.

## Tasks and acceptance

1. **Scenario contracts/injection (done):** immutable compound scenarios, order-independent versioned IDs, one component per sensor, explicit timing/seeds and bounded documented assumptions. Atomic application: if any component is inapplicable, score none of that history's compound case. Preserve legacy single-fault code and identifiers.
2. **Fixed development evaluator (done):** own a snapshot of already fitted fold models and training-only preprocessing; validate split integrity before scoring; never fit or read reserved histories. Match clean/faulted populations, report exclusions and unavailable results, bound evaluations and support cooperative cancellation. Preserve source data and thresholds.
3. **Local replay workflow (done):** new-directory export with scenario, results, checksummed fitted context and dependency/source identities; explicit trust required to load a local Python artifact. Synthetic CLI trains once then evaluates/replays without retraining. No HTTP endpoint, browser contract or cloud call.
4. **Verification/review (done):** real synthetic fitted-model tests, parity with legacy single-fault runner, compound feature correctness, coverage, no-op/unknown sensor rejection, holdout/split rejection, deterministic replay, artifact tamper rejection, limits/cancellation and independent reviews. Run fresh full backend, lint, frontend compatibility/build and CLI smoke/replay checks.

Same-sensor composition is deliberately unsupported, including disjoint intervals. Bounds are prototype measurement-corruption assumptions, not equipment-validated physical constraints. This engine is a developer seam for Phase 3; existing browser protocol setup remains single-sensor.

Decision: new-case IDs use full-precision canonical parameter hashes for both single and compound cases. Existing legacy IDs round float severities to six significant figures; a new regression reproduced a collision between distinct severities. Legacy schemas/IDs are unchanged, and numeric parity is checked using the legacy runner's own ID.

Out of scope: adaptive search, scenario reduction, remedy training, UI expansion, user-workspace training/reserved evaluation, live NVIDIA calls and cloud deployment. Isolated synthetic training fixtures are permitted for verification.

## Review and focused evidence

Independent spec, code/security and guarded data/evaluation reviewers approved the final seven-file implementation target. Initial review reproduced three issues: stale dataset caches admitted unexpected/reserved rows; mutable builder window/order escaped identity validation; and returned nested clean outcomes could poison subsequent evaluations. Regressions reproduced each before fixes. The engine now validates actual canonical rows before copying, rebuilds dataset index caches, removes unused training caches from replay, checks/hashes effective builder state, and returns defensive copies. Public policy/config/context properties are read-only.

Focused suite: **35 passed**. Guarded data reviewer also passed **41** compound/protocol/paired checks. Final synthetic CLI export and trusted replay each scored exactly **22 development histories**, preserved prediction/metric identities and made **zero provider calls**. Context fingerprint: `74ce76cb878a74cb633c06e8acd02717000a1b3e18fa565ad32c7d42844b80eb`. Package: ignored `output/phase-2-final-smoke/`.

Implementation fingerprint (sorted `path:file-sha256` pairs joined by newlines, plan/index excluded): `57f3556cbfe9bf6874d647cf133cb431e6b12ff082ac5dcd59a610b0a017d728`. Reviewed files: README, three new fault modules, CLI, focused tests and Phase 2 guide. Manifest: ignored `output/nebius-phase-2-manifest.json`.

Final frontend lint, TypeScript, **7 protocol tests**, generated API type byte comparison, production build, Ruff, CLI export/replay and diff checks pass. Existing chunk-size advisory is unchanged. Browser/UI source and API schemas did not change, so no new browser gate is claimed.

## Verification commands

- `.venv/Scripts/python.exe -m pytest -q tests/test_compound_faults.py`
- `.venv/Scripts/python.exe scripts/evaluate_fault_scenarios.py --output output/phase-2-smoke`
- `.venv/Scripts/python.exe scripts/evaluate_fault_scenarios.py --replay output/phase-2-smoke --trust-local-artifact`
- `.venv/Scripts/python.exe -m pytest -q --tb=short`
- `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`
- Generated API types compared byte-for-byte, frontend lint/typecheck/protocol/build, `git diff --check`.

## Closeout: passed (27 October 2026)

Fresh full backend gate: **500 passed, 1 skipped**, 190.11 seconds. Two existing test-library deprecation warnings remain. Final target fingerprint: `57f3556cbfe9bf6874d647cf133cb431e6b12ff082ac5dcd59a610b0a017d728`; unchanged after independent approvals and the final gate.

Exact commands: `.venv/Scripts/python.exe -m pytest -q --tb=short`; `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`; `.venv/Scripts/python.exe scripts/evaluate_fault_scenarios.py --output output/phase-2-final-smoke`; `.venv/Scripts/python.exe scripts/evaluate_fault_scenarios.py --replay output/phase-2-final-smoke --trust-local-artifact`; `.venv/Scripts/python.exe scripts/generate_types.py --output output/nebius-phase-2-types.ts` followed by byte comparison; frontend `npm run lint`, `npm run typecheck`, `npm run test:protocol`, `npm run build`; `git diff --check`.

No provider requests, user-workspace jobs, original evidence/store edits, deployment, commit or push. Synthetic training runs only used test-owned or new CLI directories. All Phase 2 changes remain **uncommitted** on `feat/nebius-investigator`, in the working tree and vulnerable to reset until saved in Git.

Next phase: expose this bounded engine to an adaptive agent with durable investigation state, explicit execution admission and a clean separation between discovery and final confirmation.
