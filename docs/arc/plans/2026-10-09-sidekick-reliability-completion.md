# Complete Sidekick reliability and AI fixes

Status: DONE (technical completion; Docker runtime verified in the authorized deployment follow-up). Reviewed application committed in a807144; merged into 97b8afd. No public deployment by this task.
Planned assurance: Guarded. Effective assurance: Guarded.
Reason: Saved cloud-derived text, access revocation, transactional capacity and paid-request identity require behavioral and privacy regression coverage.

## Deployment follow-up

On 9 October 2026 the user explicitly authorized Docker runtime verification and committing reviewed changes. The application, including the animation follow-up, was already committed in `a807144` and merged into starting HEAD `97b8afd`. The remaining Docker prerequisite is now resolved: production demo/replay and development API builds, isolated loopback Compose services, hosted memory, replay capacity, restart persistence and expiry passed. Fresh gates passed 212 backend, 68 browser and 7 protocol tests. The only new configuration fixes pin generated contract line endings and exclude browser reports/traces from Docker context. See the [deployment verification receipt](../audits/2026-10-09-sidekick-deployment-verification.md). This follow-up is committed locally; no public deployment or push was performed. Engineer benefit and field reliability remain unmeasured.

## Original implementation state (historical checkpoint)

- Starting HEAD: `046a97240e852c8818d5da6baaccd5a4e5a88cae`.
- Existing remediation work is explicitly in scope; preserve it. Initial dirty-path fingerprints: `output/remediation/reliability-baseline.json`.
- Metadata excluded from source evidence: this plan, plan index, remediation ledger and verification receipts.
- Commit posture: no commits, pushes or deployment. Worktree only, one reset away from loss.
- Closeout: passed on 9 October 2026, except the recorded Docker engine prerequisite. Source target SHA256: `2b78bd9c02eb06afd2c6280003d81df41027974edcf03f9a9b40a6c55b24d8c2` across 73 files; verification metadata excluded.
- Final results: 199 backend tests, 65 browser tests, 7 protocol tests, 12 offline assistant cases; Ruff, lint, TypeScript, generated types, production build and loopback configuration pass. Receipt: `output/remediation/reliability-closeout-receipt.json`; durable results: `TESTING.md`.
- Supporting Arc workflow references and agent descriptors are absent from the installed skill bundle. Use the available implementation instructions and repository-specific seams; no formal Arc XML validation is claimed.

## Approved behavior

New contexts automatically use live analysis when permitted. Saved answers are reused silently across analysis and brief. Normal rerun controls are removed; Retry analysis remains for recoverable unsuccessful analyses. Reads never launch AI. Historical answers remain accessible, labelled Previously saved analysis, without paid regeneration. Preserve evidence, names, ownership, source checks and routes.

## Coherent slices

| Slice | Owner and paths | Behavioral evidence | State |
|---|---|---|---|
| Provenance, access, currency, active reuse, public storage | privacy_storage: assistant store/service/schemas, assistant routes, generator/types, backend regressions | Transactional migration/revocation, owner/access/export isolation, historical GET, same active ID, replay/legacy capacity and expiry | done |
| Request lifecycle and draft revisions | analysis_lifecycle: provider/inspector/assistant client and analysis browser regressions | Delayed start hide/reopen, brief equivalence, replaced response, GET recovery, delayed save typing and export revision | done |
| Useful bounded AI | ai_usefulness: agent/investigation/evidence/data review, evaluation and focused provider tests | Fixed paths one model request, honest inspection, concrete fault action in analysis/brief, fallback and local/live rubric | done |
| Browser repairs, CI and integration | root: library/UI browser fixtures, verification workflow, documentation | Selection/menu semantics, complete drag, CSV retry/cancel, upload heading, equivalent static transforms, protocol CI, isolated synthetic workflow | done |

Dependency: provenance and access before lifecycle closeout, all provider changes before optional paid check. Each owner preserves prior dirty changes and verifies focused behavior. Generated types come only from the backend generator.

## Verification and finish

Run Ruff, all backend tests (including the isolated marked synthetic train/freeze/validation/export test), generated-type consistency, frontend lint, TypeScript, seven protocol tests, production build and relevant complete browser suites. Verify both themes, desktop/mobile, reduced motion and saved evidence/source compatibility. Run whole-implementation spec and standards review after slices settle, resolve findings, then run a fresh closeout gate. Record exact results and outstanding environmental prerequisites in TESTING.md and the remediation ledger.

Docker runtime verification requires an available engine; configuration-only success does not establish runtime success. Paid AI remains outside CI. After provider changes, at most one necessary failing-result live check is authorized: current model, no retries, at most six requests, conservative $0.10 ceiling. Do not repeat the prior full/minimal live suite. Real-equipment reliability and engineer decision benefit remain separate milestones.

## Decision log

- User explicitly authorized continuation over the pre-existing remediation changes; their ownership is established by the same conversation and baseline rather than guessed from a dirty worktree.
- Implementation skill calls for coherent owners and parallel whole-implementation reviews. Owners have nonoverlapping source paths; schema generation is backend-owned.

- Fresh whole-implementation review reproduced conversion/draft concurrency and revoked mixed-origin evidence-brief export defects; both were fixed with transactional draft merge, shared client writes and narrowly permitted sanitized evidence conversion/export. The standards reviewer reached its usage limit; the controller completed both review axes locally and did not count the interrupted response as approval.
- Browser closeout found stale animation/matrix expectations in the older clarity suite. Wait for Cult exit transitions to settle and preserve the user-approved always-expanded sensor matrix; no product behavior was weakened.

## Consolidated priority disposition

| Priority | Resolution | Evidence |
|---|---|---|
| 1. Provenance and revocation | Separate transactional origins and revocation tombstones; preserve proven evidence-only drafts and deny stale cloud writes | Migration/revocation/re-consent/late-write/owner/expiry regressions |
| 2. Reopen access and currency | GET revalidates records, capabilities and consent; historical output is labelled without paid regeneration | Denied/expired/cached/historical browser and API tests |
| 3. Draft revisions | Serialized autosave/Save/conversion; server conversion retains the current draft atomically; acknowledgements match revisions | Delayed Save and conversion interleavings, failed draft recovery, export guards |
| 4. Pending identity | Closing hides the inspector; canonical contexts share pending/active IDs; GET recovery never starts work | Delayed admission, close/reopen/brief switch, explicit replacement/cancellation, request counts |
| 5. Specific next check | Server ranking preserves inspected verified fault checks in both analysis and brief | Dropout/imputation/late/missed fixture plus one bounded live case |
| 6. AI usefulness | Fixed comparison/warning/data inspection uses one model request; evaluation measures fact/action retention, scope, repetition, latency and local parity | 12 offline cases and mocked provider tests; engineer decision benefit remains unmeasured |
| 7. Verification | Library, lifecycle, animation and replay harness repaired without weakening semantics | Final gate receipt in TESTING.md; isolated synthetic train/freeze/validate/export |
| 8. Public replay storage | Replay and demo share transactional caps and 24-hour public retention; count legacy bytes and preserve historical/local records | Capacity/concurrency/legacy/expiry/restart tests |
| 9. Protocol CI | Seven protocol tests added to the normal verification workflow | Node protocol gate and workflow command |

The application remains on its current model and theme. Changes are local and uncommitted. Docker runtime is environment-blocked until the engine is available; rendered loopback configuration passes. No field reliability or improved engineer-decision claim follows from synthetic or provider fixtures.

## Final gate commands

Provider and MLflow environment flags were disabled. Browser commands used the resolved `.venv` Python, port 8136 and isolated workspaces.

- `.venv/Scripts/python.exe -m ruff check --config pyproject.toml backend/app tests scripts`
- `.venv/Scripts/python.exe -m pytest -q`
- `.venv/Scripts/python.exe scripts/generate_types.py --output output/remediation/reliability-types-a.ts`
- `.venv/Scripts/python.exe scripts/generate_types.py --output output/remediation/reliability-types-b.ts`
- `npm run lint (cwd frontend)`
- `npm run typecheck (cwd frontend)`
- `npm run test:protocol (cwd frontend)`
- `npm run build (cwd frontend)`
- `npm test -- --reporter=line (cwd frontend)`
- `node scripts/check_local_docker.mjs`
- `node scripts/check_frontend_payload.mjs frontend/dist --loaded output/remediation/reliability-cold-route.json`
- `git diff --check`

Docker `info` was attempted separately and failed on the missing Linux engine pipe. This is an explicit environment prerequisite; every other required technical gate passed. Real-equipment and engineer benefit evaluation remains unperformed.
