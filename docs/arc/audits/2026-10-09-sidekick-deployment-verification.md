# Sidekick deployment verification

Date: 9 October 2026 (America/Chicago). Starting HEAD: `97b8afd`, including reviewed application commit `a807144`. User authorized Docker runtime verification and a local commit. No push, registry publication or public deployment was authorized or performed.

## Scope and repairs

Docker Desktop 4.44.3 failed before creating its Linux Engine pipe. Its local backend log identified an inaccessible `dockerInference` runtime socket. After stopping the failed Desktop processes, the exact `AppData/Local/Docker/run` directory was moved to a preserved adjacent backup, `run.sidekick-verification-backup-20261009`, and Desktop was started again. Engine 28.3.2 became available. No factory reset, prune, uninstall, volume deletion or WSL disk changes were used for recovery. Existing non-test containers were retained.

The initial fresh backend gate failed only because Git's Windows checkout converted the generated TypeScript contract to CRLF. The generated text matched semantically, but its byte contract did not. `.gitattributes` now explicitly requires LF for `frontend/src/api/types.ts`; the unchanged byte-for-byte regression passed after regeneration. No API/type definitions changed.

Browser traces and reports accumulated during tests and enlarged the Docker context to 161 MiB. `.dockerignore` now excludes `test-results` and `playwright-report`, alongside installed dependencies, build output, secrets and logs. Production targets were rebuilt and their final image IDs were used for runtime checks.

## Final runtime results

| Check | Result |
|---|---|
| Production demo image | Build and runtime pass; `sha256:91cc15e23ecbd140787d4f9238c4bb34e00dd7427c420193119bd3d6092a6281` |
| Production replay image | Build and runtime pass; `sha256:92b303e5dc39408977d25226478b3b5674e3dc77af1322af1e7795a7487cbc2b` |
| Development API image | Build and isolated Compose startup pass |
| Published test ports | API `127.0.0.1:18000`, web `127.0.0.1:15173`, replay `127.0.0.1:18002`; actual Docker bindings inspected |
| Frontend and proxy | Root page, full-mode health and recorded selection reachable through frontend and API |
| Demo memory | 512 MiB hard memory/swap limit, 266.26 MiB peak sampled working set, 266.37 MiB sampled current memory, 268.87 MiB cgroup peak; OOMKilled=false |
| Demo workflow | Synthetic sample train, decision, replay index, report and ZIP export pass in 7.73 seconds; metrics rows match exported evidence; second visitor gets 404 |
| Replay restrictions | Recorded evidence available; training disallowed; upload/freeze/validation capabilities off; live AI unavailable; evidence-only analyses and direct routes available |
| Record capacity | Test cap 2 records / 1 MiB: 2 admitted, next admission 503; existing results readable, reusable, convertible, editable and exportable |
| Byte capacity | Separate fresh container, 2,000-record cap / 150,000 bytes: 1 admitted, next admission 503; existing record remains usable |
| Replay ownership | A separate cookie jar cannot read the first visitor's analysis (404) |
| Restart persistence | Existing ID and explicitly saved brief retained after container/server restart; capacity remains enforced |
| Public retention | Only test-owned public record aged beyond 24 hours; GET/export return 404; next admission succeeds without deleting retained records to evade a cap |

All containers used test-only writable storage. Compose overrides used new named volumes instead of the user's data and artifacts, alternate loopback ports, a read-only frontend mount and `npm ci`. API credentials were explicitly blank and live AI was disabled. Paid provider calls: zero. Synthetic training was limited to verification fixtures. Test containers and their temporary Compose volumes were cleaned up; built verification images and the preserved Docker runtime backup remain local.

Final hosted image training dependencies: NumPy 2.4.6, pandas 2.3.3, scikit-learn 1.9.1, XGBoost CPU 3.2.0 and joblib 1.6.0. These are the fresh image's recorded dependencies, not modifications of previous experiment evidence. Its synthetic source digest was `c2c4898aff6ae087c9f7885cda2c4645b16683faaccd85dafe4bd93fd9601b2c`.

## Gate and commands

- Ruff: pass.
- Backend: 212 passed, including isolated synthetic integration and launcher tests. The initial line-ending failure was repaired and the full suite rerun.
- Frontend: lint, TypeScript, 7 protocol tests and production build pass.
- Browser: 68 passed in 5.6 minutes, including lifecycle, saved drafts, library, motion, both themes/mobile and synthetic train/freeze/validate/export.
- Generated types: exact byte comparison passes after LF regeneration.
- Whitespace and staged diff: checked before commit.

Commands used from the repository root, except npm commands from `frontend`:

```text
.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/generate_types.py
npm run lint
npm run typecheck
npm run test:protocol
npm run build
npm test -- --reporter=line
node scripts/check_local_docker.mjs
docker build -f docker/api.dev.Dockerfile -t sidekick-verify-api:20261009 .
docker build --target demo -t sidekick-verify-demo:20261009 .
docker build --target replay -t sidekick-verify-replay:20261009 .
docker compose -p sidekick-verification-20261009 -f docker-compose.yml -f output/deployment-verification/compose.override.yml up -d --no-build
docker exec sidekick-verification-memory-final-20261009 python /tmp/check_hosted_memory.py
docker exec sidekick-verification-replay-final-20261009 python /tmp/replay_runtime.py
docker restart sidekick-verification-replay-final-20261009
docker exec sidekick-verification-replay-final-20261009 python /tmp/replay_runtime.py --resume
docker exec sidekick-verification-replay-bytes-20261009 python /tmp/replay_runtime.py
git diff --check
```

The hosted-memory checker is the existing `scripts/check_hosted_memory.py`. The guarded HTTP replay harness, isolated Compose override and final memory JSON are retained under ignored `output/deployment-verification/`. Replay record/byte limits were reduced solely in disposable containers to exercise admission failures without generating thousands of records. Runtime retention was exercised by aging only a captured test record in its isolated SQLite file, rather than waiting 24 hours. Defaults remain 2,000 records and 32 MiB.

Scope review: only the two build/checkout configuration fixes and verification metadata belong to this follow-up. Existing application/evidence/source compatibility rules and original audit receipts were preserved. The prior blocked/uncommitted statements describe earlier checkpoints. This resolves the Docker prerequisite; it does not establish public infrastructure readiness, real-equipment reliability or measured engineer/AI benefit.
