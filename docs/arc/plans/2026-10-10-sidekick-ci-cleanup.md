# GitHub failures and safe project cleanup

Status: DONE (runtime cache deletion blocked by host policy)
Planned assurance: Standard
Effective assurance: Standard. Evidence packaging is fingerprint-sensitive; preserve exact bytes and test both Git line-ending modes and archive/checkout output. No evidence loader, database or access-policy changes.

## Implementation state

- Baseline: `d54a41276d01c9ec5456a632f2f6023601169454`; clean worktree.
- One local owner. User explicitly requested no subagents; perform completion and correctness review locally.
- Full Arc workflow references are absent from this installation. Use repository checks; no formal bundle validation claimed.
- Leave changes uncommitted and unpushed. No remote workflow reruns or paid AI requests.
- Latest failure: [run 38027263024](https://github.com/Havocx01/SideKick/actions/runs/38027263024), verify job 114140643190. Backend, build and hosted-memory passed; nine browser failures.
- Previous run: [38025238234](https://github.com/Havocx01/SideKick/actions/runs/38025238234), eight replay-related failures.
- Recorded bundle SHA-256 on disk: `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`. Git's LF blob: `9619493c03ca899ee3f8840218dc237a57e2c0b8fdfd99a1e6436cefac2f485d`. Content differs only in line endings; the supplement requires the first exact hash.
- Original bytes are unchanged on disk. Git reports the newline-only bundle change needed to publish those bytes instead of its previously normalized blob. `git diff --ignore-space-at-eol --exit-code -- evidence/bundle.json` is empty. The index remains unstaged.
- Paths: `.gitattributes`, `.gitignore`, `.dockerignore`, `.github/workflows/verify.yml`, `tests/test_evidence_checkout.py`, `frontend/tests/library.spec.ts`, `frontend/src/components/Layout.tsx`, `frontend/components/arc/motion-tokens.ts`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/styles.css`, unused `WalkthroughSpotlight.tsx`, `WalkthroughSpotlight.css`, and `cult/WalkthroughProgress.tsx`. Documentation: `TESTING.md`; this plan and its index are metadata.
- Protected: data, artifacts, output backups/evaluation packets, evidence bytes, project documents/media, installed runtimes and unrelated processes.

## Work

<task id="ci" kind="behavior" status="done">
  <scope>Preserve checksum-bound bundle bytes in Git archives/checkout, retain checksum rejection, scope the library status assertion and keep failure diagnostics available.</scope>
  <done>Regression tests prove both line-ending modes retain exact bytes and supplemental replay without changing metrics. Failed checksum is rejected. Affected browser suites remain behaviorally strict.</done>
  <verify>pytest tests/test_evidence_checkout.py -q; npm test -- tests/clarity.spec.ts tests/library.spec.ts tests/walkthrough-interactive.spec.ts tests/workflow.spec.ts --grep-invert 'a browser sample trains'</verify>
</task>

<task id="cleanup" kind="refactor" status="done">
  <scope>Remove import-graph-confirmed unused walkthrough files/dependency/styles; replace identical duplicated motion presets with a re-export. Exclude disposable outputs from Git/Docker. Remove only checked cache paths.</scope>
  <done>Application, lazy routes, both themes, motion and walkthrough remain covered. No personal workspace content or durable reports removed.</done>
  <verify>npm run lint; npm run typecheck; npm run test:protocol; npm run build; offline backend and browser gates; git diff --check</verify>
</task>

## Review and closeout

Closeout: passed, 10 October 2026. Attributable fingerprint:
`0939c2325a0d38c22bcb65d96b19a91c88ea66ee8d2bfba588dcedfd4ac001ff`.
Fifteen changed/deleted/new implementation paths, excluding plan/index metadata.
Session receipt: ignored `output/ci-cleanup-review-target.json`.

Local completion and correctness reviews covered the same unchanged target:

- The eight older replay failures and newer ninth library status failure are addressed without skipping browser tests, relaxing checksum verification or modifying the evidence loader.
- Packaging regression reproduced the failure before the attribute fix. Both `core.autocrlf` modes, ZIP archives, checkout output, supplemental replay availability, unchanged scenario metrics and altered-byte rejection now pass.
- Import traversal from the application entry, including lazy imports and aliases, identified two unused walkthrough components. Their old stylesheet and four unused progress rules were removed. The present Cult walkthrough remains covered by browser tests.
- Removed only `driver.js` from dependencies. Arc motion definitions matched the canonical registry object exactly before replacing the duplicate with a re-export. No animation presets changed.
- Ignored/excluded local frontend diagnostics and case variants of environment files; `.env.example` remains tracked. CI saves failed browser traces/HTML reports for seven days.
- Preflight found 16 disposable cache directories (about 3 MB), refused outside-workspace/linked contents, and recorded paths in `output/ci-cleanup-cache-preview.json`. **Deletion was blocked by automatic safety review**, first for validated computed paths and then for explicit literal paths; the only reason returned was "blocked by policy." Caches remain intact. No alternate tool or script was used to bypass the block. This optional scope item is environment-blocked, not completed deletion.
- Data, artifacts, backups, evaluation packets, project documents/media, virtualenv and unrelated processes retained.

Fresh verification:

- `python -m ruff check --config pyproject.toml backend/app tests scripts`: passed.
- `python scripts/generate_types.py` and `git diff --exit-code frontend/src/api/types.ts`: passed.
- `python -m pytest -q`: **246 passed, 1 skipped** in 117.51 seconds. Includes the isolated synthetic training/freeze/validation/export test. Windows native symlink creation lacks permission; crafted archive defenses remain tested. Two upstream test-client deprecation warnings are nonblocking.
- `npm ci --no-audit --no-fund`, frontend lint, TypeScript, **7 protocol tests**, production build: passed. Existing Vite size advisory remains visible.
- `npm test -- --reporter=line`: **68 passed** in 5.4 minutes, including the synthetic browser training/freeze/validation/export workflow, replay, library, actual motion, both themes and 390 px layouts.
- Workflow YAML/failure artifact wiring, zero unreachable frontend modules, Compose loopback configuration, whitespace checks and unchanged raw evidence checksum: passed.
- No provider calls. All job-producing tests use isolated fixtures/workspaces.
- Docker runtime repeat was unavailable because the local engine is stopped. The latest inspected GitHub `hosted-memory` job passed; configuration validation passed locally. No container runtime claim is made for this session.

Changes are **uncommitted and unpushed**. The existing GitHub failure is historical and cannot turn green until the fix, including the exact-byte bundle, is committed and pushed. This task did not rerun unchanged failing remote code or mutate GitHub.
