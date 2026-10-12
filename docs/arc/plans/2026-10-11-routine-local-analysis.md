# Retire automatic AI from routine analysis

Status: DONE. Planned/effective assurance: Guarded, for provider admission, saved-output compatibility and privacy. Single owner; no subagents. Source changes remain uncommitted and undeployed. No training or paid requests.

## Implementation state

Starting HEAD: `3b0d54c951634e09bbe64731635d1f4bc3e6742b`. Working tree clean before edits. Scope: assistant service/routes, provider/inspector/settings UI, existing assistant tests, a routine-path boundary suite, workspace browser checks and current documentation. No changes to environment files, real assistant storage, datasets or evidence. Plan/index metadata excluded from the verification target.

## Agreed changes

1. Routine analysis creation is always local across investigate, compare, warning, brief and data, regardless of key/permission/mode. Retain the legacy provider through an explicitly internal entry point for offline regression coverage until its replacement is verified. No replacement deep-investigation feature is introduced in this cleanup.
2. Capabilities advertise no live routine generation or presenter unlock UI. Preserve permissions and historical cloud-read/export safeguards, record ownership, reuse, cancellation and public storage limits. Saved permitted AI answers remain accessible and clearly labelled saved output. Regular failures still support local Retry; provider setup/fallback controls leave routine panels.
3. Preserve ordinary analysis, comparison, replay, mapping and editable/exportable briefs. Remove permission/presenter prompts from routine inspectors. Retain workspace settings for revocation and saved-output access, with accurate copy that permission does not start new requests. Keep historical schemas/IDs and the three-claim regular format.
4. Update obsolete automatic-AI documentation/tests; legacy-provider tests move to the explicit internal seam, retaining safeguards. Prove zero provider calls on every public routine task, including direct brief creation and conversion, plus historical saved reuse and revoked access. Keep the existing evaluation script gated and document it as legacy, not evidence for a new deep system.

## Verification

Start with failing API/CSV boundary tests. Run focused assistant tests, frontend lint/types/protocol/build and analysis/permission browser fixtures, then offline backend tests. Verify no AI setup in ordinary results at desktop/mobile, saved IDs and drafts, all-owner revocation, no API generation escape, and unchanged evidence. Local completion, correctness/privacy and UI reviews substitute for agents at the user's instruction. Record exact results; leave source changes uncommitted.

## Reviews and results

Local completion and correctness/privacy reviews inspected the attributable diff, all new test cases, route admission, historical reuse/access, brief provenance, active-job separation and permission recovery. Arc copy/accessibility/theme review reused existing controls, checked screenshots at 390 and 1280 px in both themes, and retained the established responsive/motion system. No new library or public schema was introduced. The legacy selector and its safeguards remain explicitly internal; replacing that engine with an evidence-grounded deep report is the next feature, outside this cleanup. No remaining in-scope findings were identified.

Initial boundary checks: five expected failures before the server change, one guard case already passed. Six then passed, followed by coverage expansion to 17. The full suite exposed a timing assumption in the active mocked-provider fixture; an explicit entry event now proves the provider is running before checking public/legacy separation, without weakening the assertions.

Closeout: passed, 11 October 2026. Target SHA-256 `6c84edb377c5b41744ce1165cdfde7020d52689754fc5a88666a8f38b10b5bfe` over sorted `path:file-sha256` pairs for the 15 source/test/current-documentation paths, including the new routine test file and excluding plan/index metadata. HEAD remains `3b0d54c951634e09bbe64731635d1f4bc3e6742b`.

- `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`: passed.
- `.venv/Scripts/python.exe -m pytest tests -m 'not integration' -q --tb=short`: 268 passed, one Windows symlink permission skip, three integration tests deselected; 48.61 seconds. Live evaluation and MLflow disabled.
- `.venv/Scripts/python.exe -m pytest tests/test_routine_analysis.py -q --tb=short`: 17 passed after the fixture synchronization fix, 11.69 seconds.
- `.venv/Scripts/python.exe scripts/generate_types.py --output output/routine-analysis-types.ts`: exact SHA-256 match with frontend types.
- `.venv/Scripts/python.exe scripts/evaluate_assistant.py --output output/routine-analysis-offline-evaluation.json`: 12 local cases passed; zero provider requests, unchanged evidence and no training jobs.
- From `frontend`: `npm run lint`, `npm run typecheck`, `npm run test:protocol` (seven passed), `npm run build`: passed. Lint/types were repeated after the final visual/code review. Existing bundle-size advisory remains.
- From `frontend`: `npm test -- tests/workspace-ai-permission.spec.ts tests/analysis-recovery.spec.ts tests/investigation.spec.ts tests/ui-regressions.spec.ts tests/motion-preference.spec.ts --reporter=line`: 39 passed in 2.4 minutes, isolated fixture workspace.
- `git diff --check` and unchanged generated-type Git diff: passed. No real assistant storage, environment secrets, dataset or recorded evidence changed. No paid requests or subagents.

Restart the local server and refresh the app to load this change. Existing routine actions stay available; there is no new deep-investigation button yet. Current documentation distinguishes public local workflows from separately authorized legacy evaluation.
