# One AI permission for the local workspace

Status: DONE. Planned/effective assurance: Guarded (privacy, access and cancellation). Single owner; no subagents. Implementation remains uncommitted and undeployed. No provider calls made.

## Baseline and scope

Starting HEAD: `9cf4ce7`. The preceding motion/startup changes remain uncommitted and are retained. Their source/test paths do not overlap this task; TESTING.md and the plan index are shared documentation owned in this conversation. No environment files, uploaded CSVs or recorded evidence are edited.

Scope: assistant store/service/routes, analysis provider/inspector, a themed workspace AI settings control, assistant boundary tests and fixture browser checks. Existing analysis/result ownership remains browser-scoped. Hosted demo and replay do not gain workspace-wide permission.

## Implementation

1. Add a repeatable transactional singleton permission table, defaulting to no workspace approval. Never broaden a legacy scoped grant automatically. Preserve legacy saved-output access until a workspace permission is deliberately set.
2. Full-mode creation and capabilities use workspace approval across all experiment/dataset contexts. Existing scoped consent endpoints remain compatible aliases in local mode. Turning off atomically clears cloud/unknown output and cancels all workspace jobs while retaining evidence-only drafts and revocation tombstones.
3. Upgrade a cached consent-only fallback after explicit approval once, then reuse saved AI across analysis/brief. Do not turn model/version changes or provider failures into automatic paid retries.
4. Keep one independent AI settings control accessible before opening analysis. Initial analysis approval explains its workspace scope. Setting changes invalidate stale client work; saved setting lives on the server across browser/server restarts.

## Verification

Red workspace tests: all three failed before implementation. Verify approval across contexts/browsers, restart, origins/guards, public-mode denial, revocation before cancellation, safe draft retention and one mocked enhancement followed by shared reuse. Update existing mocked provider tests to explicitly approve the workspace without weakening failure/ownership assertions. Check both themes, 390 px keyboard/dialog layout and failed permission saves with fixtures. Run assistant/backend tests, generated-type consistency, Ruff, frontend lint/types/protocol/build and relevant browser suites, then perform local completion/correctness reviews.

## Review and decisions

Completion and correctness reviews were performed locally, followed by privacy/access and accessibility review; no agents were spawned. Workspace approval covers all full-mode contexts while demo/replay deny the workspace route. Scoped routes remain compatible aliases in full mode. Approval, output ownership and immutable evidence remain separate. Legacy grants are not promoted; historic scoped output remains readable until an explicit workspace decision. Revocation commits the permission, scrubs all owners' cloud/unknown fields and tombstones records before cancellation awaits. Future-contract JSON retains identifiers while its private fields are cleared. Late writes and reapproval cannot resurrect revoked content.

One permission-only fallback upgrades after approval; provider failures and historical model/prompt changes do not cause automatic paid retries. Client focus/storage recovery verifies completed output with GETs, not new jobs. Failed permission saves retain the UI state and show an adjacent error. Both theme screenshots at 390 and 1280 px were inspected; keyboard focus, dismissal and viewport bounds passed. No unresolved in-scope findings remain. Existing bundle-size and dependency deprecation advisories remain outside this permission change.

## Implementation state

Closeout: passed, 10 October 2026. Starting/current HEAD `9cf4ce7`; changes remain only in the working tree. Target SHA-256 `f019560487bd5e0a7e915b4e31ed15898d3faebbeae5cb94684786792a634020`, computed over the sorted `path:file-sha256` pairs for this task's assistant source, frontend source, boundary/browser tests, README and TESTING. Plan/index metadata are excluded. Prior motion/startup changes are retained, and the shared documentation intentionally contains both tasks.

- `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`: passed.
- `.venv/Scripts/python.exe -m pytest tests -m 'not integration' -q --tb=short`: 251 passed, 1 Windows symlink permission skip, 3 integration tests deselected, 82.08 seconds. Live AI and MLflow disabled; no training.
- Focused `tests/test_workspace_ai_consent.py tests/test_assistant_api.py`: 55 passed after final backend changes, including mocked active jobs, historical contracts and all-owner API read/conversion/export denial.
- `scripts/generate_types.py --output output/workspace-types-check.ts`: exact SHA-256 match with frontend types; generated public shapes unchanged.
- From `frontend`: `npm run lint`, `npm run typecheck`, `npm run test:protocol` (7 passed), `npm run build`: passed.
- From `frontend`: `npm test -- tests/workspace-ai-permission.spec.ts tests/analysis-recovery.spec.ts tests/investigation.spec.ts tests/ui-regressions.spec.ts tests/motion-preference.spec.ts --reporter=line`: 38 passed, 2.6 minutes; fixture workspace, no paid requests.
- `git diff --check`: passed. No environment, dataset or recorded-evidence edits. No public deployment or commit.

User activation: restart the local app, open **AI settings**, and enable once. This implementation does not alter the user's live permission database during development or tests. The server still requires configured provider access; saved answers remain reusable without rerunning.
