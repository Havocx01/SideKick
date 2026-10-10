# Sidekick backup, startup and engineer evaluation

Status: DONE. Planned assurance: Guarded. Effective assurance: Guarded.

Backup restoration touches durable evidence, privacy metadata and the reserved-history exposure ledger. Restore must create a new workspace and never merge into or replace existing data. Performance and evaluation work use offline recorded fixtures.

## Implementation state

- Implementation baseline: `7b70511283be97d8511c9b104501737f3e97fa6b`.
- Pre-existing dirty paths: none.
- Commit posture: leave changes uncommitted; no push or deployment.
- Declared paths: new `scripts/workspace_backup.py`, `tests/test_workspace_backup.py`, `docs/workspace-backup.md`; `tasks.ps1`, `README.md`, `TESTING.md`; frontend startup import seams and focused payload/motion tests; new `scripts/prepare_engineer_evaluation.py`, `tests/test_engineer_evaluation_pack.py`, `docs/engineer-evaluation-pack.md`. Plan/index metadata excluded from implementation evidence.
- Supporting Arc reference/agent files are absent from this prompt-only installation. Explicit slice boundaries and review criteria substitute; no formal bundled XML validation claimed.
- Closeout: passed, 10 October 2026, on starting HEAD `7b70511283be97d8511c9b104501737f3e97fa6b` plus the uncommitted attributable changes.
- Attributable target: 15 files; SHA-256 over sorted `path:file-sha256` lines: `241dd119e3b1061746ec6fa17a3333851472e587da45f741f61b6af35bfce7a0`. File list and hashes: ignored `output/next-improvements/closeout-target.json`. Plan/index metadata and the concurrent CSS change are excluded.
- Whole-spec and standards review: approved after credential-case, path validation and evaluation-parity/context fixes. Guarded backup security/data review: clear after fixes. No unresolved material findings.
- Fresh backend gate: Ruff, regenerated-type consistency, **242 passed / 1 skipped / 1 integration deselected**; two unchanged test-library deprecation warnings. Docker Compose loopback checker passed. Commands below.
- Fresh frontend gate: lint, TypeScript, **7 protocol tests**, production build and **67 browser tests** passed (3.6 minutes). The training browser workflow was deliberately excluded. Vite's chunk-size advisory remains visible.
- Final production cold-route measurement: **575,054 raw / 177,919 gzip bytes** (new hashed assets slightly change gzip from the earlier controlled 177,920). Observed final timings: 860 ms overview / 422 ms first analysis. Claim the measured loading-byte reduction, not a proven latency improvement. Receipt: ignored `output/performance-improvement/closeout.json` and `.timings.json`.
- Final actual PowerShell fixture commands `backup`, `verify-backup`, `restore` passed in OneDrive (`output/recovery-smoke-20261009-235838/powershell-backup.zip` and `final-restored`). Linux closeout fixture passed WAL, `flock`, preserved bytes, no-overwrite, uppercase env exclusion and native source-symlink rejection (`cea042`). It used an automatically removed network-disabled container with only the script bind-mounted read-only. Recipe: ignored `output/next-improvements/linux-recovery-fixture.py`.
- Work exists only in the uncommitted worktree; it is not backed up by the existing GitHub commit and can be lost by resetting. No commit, push or deployment performed. User workspace/evidence retained; actual user data was not backed up by these fixture checks.
- Concurrent unrelated change: `frontend/src/views/data-protocol.module.css` acquired a `margin-bottom: 20px` addition during execution. Preserve it; exclude it from this task's attributable review/fingerprint. Observed SHA-256: `bcc808e7c837cab4545a3eed2c99132e50cf37db3cb9609d972dd24b577a7a3f`.

## Slice receipts and decisions

- Recovery focused gate: 21 passed, 1 Windows native-link-permission skip. ZIP symlink rejection executes without native-link permission. PowerShell fixture restore and checksum verification passed in OneDrive. Publication uses verified copying after a real Windows cloud-sync directory-rename error; partial destinations are exclusively owned and cleaned on failure. Linux final fixture passed WAL, `flock`, bytes, no-overwrite, `.ENV` exclusion and native source-symlink defense (auto-removed network-disabled container, only script mounted read-only; primary tool receipt `303dc6`).
- Startup cold-route bytes: 663,253 → 575,054 raw; 208,117 → 177,920 gzip. Timings 791 → 796 ms overview / 349 → 480 ms first analysis do not prove reduced latency. Six frontend files changed; motion implementations were untouched. Build/lint/typecheck, payload + motion tests and repeated payload observations passed at the slice boundary.
- Engineer pack: 12 cases / 8 deterministic brief examples / 4 synthetic CSVs; 10 focused tests. Reviewer and answer-key HTML checked at 1280 px and 390 px. Final generated packet: `output/engineer-review-packet-20261010-reviewed`. No AI answer or study outcome fabricated. Both methods expose the same four CSV links. Alternate bundle selection is checked against the fixed rubric before writing output.
- Whole-implementation review and final gate passed. No paid AI or real training/validation jobs. Source-symlink creation on Windows is environment-blocked; fixture ZIP symlink defense and Linux native source-symlink defense are verified. Real engineer participation remains required to conduct the study.
- Independent review fixed Windows-case environment-file exclusions and malformed dot ZIP names. All path/printed-path inputs now expand `~`. Review also required equal CSV access and valid alternate-bundle contexts in the engineer pack; final review of those fixes follows.

## Tasks

<task id="backup" kind="behavior" status="done">
  <scope>Offline consistent snapshot of configured local data/artifacts and recorded bundle, with checksums, database integrity, stopped-server/active-job protection, secret exclusion and no-overwrite restoration into a fresh workspace.</scope>
  <done>Fixture restoration retains IDs, mapping, evidence bytes, folders, briefs, provenance, revocation and exposures. Malformed archives and failed operations leave existing data untouched.</done>
  <verify>.venv/Scripts/python.exe -m pytest tests/test_workspace_backup.py -q</verify>
</task>

<task id="startup" kind="performance" status="done">
  <scope>Measure production cold-route resources and selectively defer unused code while preserving navigation, first analysis and motion preferences.</scope>
  <done>Actual downloaded byte reduction documented; startup/first-action timings reported without claiming a benchmark guarantee; focused browser checks pass.</done>
  <verify>npm run build; npm test -- tests/payload.spec.ts tests/motion-preference.spec.ts --reporter=line (frontend)</verify>
</task>

<task id="evaluation" kind="artifact" status="done">
  <scope>Generate reviewer cases, a separate verified answer key and blank score sheets from recorded/offline evidence without provider calls or training.</scope>
  <done>Evidence context/fingerprints retained, reviewer/answer materials separated, generated artifacts inspected, no invented study outcomes.</done>
  <verify>.venv/Scripts/python.exe -m pytest tests/test_engineer_evaluation_pack.py -q</verify>
</task>

## Final review and gate

Review the same attributable diff for scope completion, standards and backup security/data integrity. Run Ruff, offline backend tests (`-m "not integration"`), frontend lint/typecheck/protocol/build and affected browser suites (`--grep-invert "a browser sample trains"`) after final fixes. The unchanged lifecycle tests launch only sleeping stub workers; no actual model is trained. Record results and remaining external prerequisite: a real engineer is needed to conduct the study. No paid AI, real training or validation jobs are authorized here.

Executed from the repository root with live AI/evaluation disabled and MLflow disabled:

```powershell
.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv/Scripts/python.exe scripts/generate_types.py
git diff --exit-code frontend/src/api/types.ts
.venv/Scripts/python.exe -m pytest -q -m 'not integration'
node scripts/check_local_docker.mjs
git diff --check
node scripts/check_frontend_payload.mjs frontend/dist --loaded output/performance-improvement/closeout.json
```

Executed from `frontend` with `SIDEKICK_TEST_PYTHON` pointing to the root virtualenv and `SIDEKICK_PAYLOAD_OUTPUT` pointing to the closeout receipt:

```powershell
npm run lint
npm run typecheck
npm run test:protocol
npm run build
npm test -- --grep-invert 'a browser sample trains' --reporter=line
```

Cross-platform recovery smoke:

```powershell
Get-Content output/next-improvements/linux-recovery-fixture.py -Raw | docker run --rm -i --network none --memory 512m --entrypoint python --mount 'type=bind,source=C:\Users\adamq\OneDrive\Desktop\Projects\Project-ABB\scripts\workspace_backup.py,target=/app/scripts/workspace_backup.py,readonly' sidekick-verify-replay:20261009 -
```
