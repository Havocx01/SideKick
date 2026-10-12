# Latest release and UI verification

12 October 2026. Reviewed application commit `556fc2b72d2d0cf89183adfc08d29b15ab62990c`. One local owner, no subagents, zero paid requests. No user experiments, consent, briefs or evidence were edited. Synthetic training and validation were limited to disposable verification stores.

## GitHub result and repair

[GitHub run 38186580834](https://github.com/Havocx01/SideKick/actions/runs/38186580834) completed with a failure: three context-save browser assertions matched two status elements. Backend (**410 passed, 2 skipped**), Ruff, generated types, frontend lint/typecheck, seven protocol tests, production build, Compose validation and hosted-memory checks passed. The remote browser suite reported 100 passed and three failed. This is not a green remote release gate.

The local repair scopes the assertion to the **Context saved** status. It still checks a failed save retains the values and prevents starting, successful save completes, context is sent on Start, and only one analysis is admitted. No waits, retries or weakened behavior checks were added. Fresh local verification: focused deep suite **20 passed**, complete browser suite **103 passed**, frontend lint and Compose validation passed. Changes are uncommitted/unpushed; GitHub remains red until the repair is published and a new run passes. No remote rerun of unchanged code was requested.

## Fresh packaged runtime

Both production targets were built from the current app source. The replay container's bundle and warning-trace implementation SHA-256 hashes match the workspace originals.

| Check | Fresh result |
|---|---|
| Demo image | `sha256:15ccb81821ef3d63a042a7131212d46ae3fd1e060a6791fb8bef1ced86b8a4e1`; build and runtime pass |
| Replay image | `sha256:6227a2c13d6e4547d72eb184774e2b4ee8c474f26f3ff6995f381d72088ca8b2`; build and runtime pass |
| Bindings | Demo `127.0.0.1:18100`, replay `127.0.0.1:18102`; actual bindings inspected |
| Demo workflow | Synthetic train, decision, replay index, report, ZIP/evidence consistency and second-visitor 404 pass in 5.65 seconds |
| Demo memory | 512 MiB memory/swap cap; 267.13 MiB peak sampled working set, 267.98 MiB sampled current, 271.73 MiB cgroup peak; OOMKilled=false |
| Replay restrictions | Recorded routes available; upload/training/freeze/validation unavailable; live AI off |
| Record capacity | Two-record test cap: two admitted, next admission 503; saved records reusable, editable, convertible and exportable |
| Byte capacity | Separate disposable container, 150,000-byte cap and 2,000-record cap: one admitted, next admission 503 |
| Ownership | Other visitor cannot read the saved record (404) |
| Restart | Saved ID/draft and capacity retained |
| Expiry | Test-only public record aged beyond 24 hours: read/export 404; replacement admitted |

The hosted CI job independently passed with 272.34 MiB sampled working set and 275.07 MiB cgroup peak. These measurements include different fixture runs and monitoring, not a general memory guarantee for arbitrary uploads.

Docker Desktop initially failed to start because its inference runtime socket could not be accessed. With no Desktop/backend process running, the resolved exact runtime directory was preserved as `C:/Users/adamq/AppData/Local/Docker/run.sidekick-verification-backup-20261012`; Desktop recreated its sockets and Engine 28.3.2 started. No factory reset, prune, volume deletion or WSL disk modification. Existing container `reconner` was retained. Test containers have distinct names/storage; no user directories were mounted.

## Browser walkthrough

An AI-operated Playwright walkthrough inspected the freshly packaged **replay** app: introductory healthy/faulted steps, Data and protocol, Transition selection, Reserved validation, 390 × 844 mobile/light and mobile/dark, and 1280 × 720 desktop/dark. The transition exclusion and historical exposed-holdout status rendered correctly; navigating did not score validation or start training. Screenshots and snapshots are in ignored `output/playwright/release-review-20261012/` and `output/release-review-20261012/`.

The desktop protocol overview is compact and its recorded scope is visible. On mobile, natural vertical scrolling is required for the bottom of the selected reserved explanation/exposure notice. This is not clipped content, but comprehension of that notice deserves a first-user check. No human success rate, comprehension, frustration or completion time was inferred. Upload/library/full-mode actions are covered by the automated suite, not a live first-time participant observation. [Session materials](../../sidekick-review-sessions.md) provide tasks to test that milestone.

## Evidence and limits

Recorded bundle SHA-256 remains `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`; replay supplement remains `3f3092bf6e8ba1d965ca275e3581082c0ee90a38ab44a5c5ee9e460201cd1166`. Both are unchanged. Logs, generated review packs, container receipts and image IDs are retained under ignored `output/release-review-20261012/`.

Technical runtime checks and local browser repair are complete. Remote CI needs the local repair published. A real-equipment pilot and human/engineer comparison remain unperformed; the [AI-assisted engineering assessment](2026-10-12-engineering-assessment.md) is a separately labelled technical review, not field proof or measured human benefit.
