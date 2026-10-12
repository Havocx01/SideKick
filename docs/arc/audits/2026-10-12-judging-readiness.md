# Judging readiness — 12 October 2026

Single owner, no subagents. Baseline `556fc2b72d2d0cf89183adfc08d29b15ab62990c`.
This closeout includes the previously authorized local release, trace-specific AI
and action-layout changes. No push, public deployment or new paid model request.
Exact final local commit identification is retained in ignored
`output/judging-20261012/release-manifest.json` and Git history.

## Outcome

Sidekick is ready for a supervised recorded-evidence presentation rehearsal. Local
technical checks and packaged demo runtime pass. Publishing the reviewed commit,
green remote CI, physical presentation-laptop/display rehearsal and organizer
confirmation remain separate steps. No human usability study or field validation
has been substituted by automated checks.

Corrected stale v1.5 handoff/walkthrough instructions. Added the
[five-minute/two-minute judging guide](../../judging-guide.md), a silent current V2
browser recording, seven screenshots, an offline HTML report, saved review ZIP and
recorded evidence ZIP. The main story uses lr2's 80/80 healthy versus 41/80 weakest
dropout detection and aug3's separately recorded 64/64 required-case result.
These are simulated-engine development results, not ABB field data or causal proof
that augmentation improved performance.

Final review fixed two correctness issues:

- Deep output currency now hashes `trace_reasoning.py` alongside the existing
  contracts. A changed trace-admission contract labels saved output historical;
  GET and eligible reuse preserve its ID without buying a replacement. The focused
  regression failed before the change and passed afterward.
- Guidance for a retained faulted warning says that both counterparts retain
  warnings only when their recorded useful-window states support it. A clean
  missed-warning fixture preserves that distinction without fabricating an outcome.

ESLint excludes generated Playwright output directories. Its initial concurrent
walk encountered a cleanup race. An initial browser attempt also overlapped Vite's
replacement of `dist`; it was stopped, then the entire suite ran successfully
against the completed build. Neither failed attempt is counted as a passing gate.

## Verification

| Check | Final result |
|---|---|
| Ruff | Pass |
| Backend, including synthetic integrations | **439 passed, 1 skipped**; 117.24 s |
| Generated API types | Byte-identical to checked-in contract |
| Frontend lint and TypeScript | Pass; TypeScript also runs in production build |
| Protocol tests | **7 passed** |
| Production build | Pass; existing >500 kB chunk advisory remains |
| Complete browser suite | **105 passed**, 5.1 min |
| Cold API start / restart | **1.594 s / 1.610 s** in isolated full-mode storage |
| Brief persistence | Same ID, exact saved text and export available after restart with the same owner cookie |
| Offline recording | Seven screenshots, **24.68 s** silent video, zero page errors; external traffic blocked; no training/AI |
| Portable HTML / ZIP | Seven images and video load from disk; offline report opens; ZIP integrity and allowlist pass |
| Fresh Docker demo build/runtime | Pass; synthetic train, decision, replay index, report, evidence ZIP consistency and second-visitor 404 |
| Docker memory | 512 MiB cap; **269.64 MiB** peak sampled working set, 269.77 MiB sampled current, 271.27 MiB cgroup peak; OOMKilled=false |
| Local Compose bindings | Pass, loopback-only published ports retained |
| Public demo read-only smoke | Health 200, V2 demo mode, routine analysis available, live/deep AI off; no paid/sample job started |
| GitHub | Latest inspected run **38186580834 failed** on baseline commit; this local revision has not been published |

Browser checks cover keyboard/context navigation, library selection/rename/dragging,
CSV failures/retry/cancellation, mapping/context setup, themes and 390 px layouts,
motion preferences, saved-record reuse/access/revocation, draft revision races,
review/export and synthetic train → freeze → validate once → export. The final
backend wording repair occurred after the browser run; it changes server-composed
deep guidance only, keeps UI/public contracts unchanged, and passed the complete
backend gate and fresh Docker build afterward.

The fresh Docker run completed in 3.89 seconds. Memory measurements describe this
bounded synthetic sample, not arbitrary uploads. Earlier disposable replay
capacity, expiry, ownership and restart checks remain recorded in
[release runtime review](2026-10-12-release-runtime-review.md); they were not repeated
or mislabelled as fresh checks. Only this task's disposable containers were removed.
The existing unrelated container and the user's port-8140 API were retained.

## Offline package and privacy

`output/judging-20261012/sidekick-presentation-kit.zip` contains an allowlisted
14-file package: `presentation.html`, guide, video, screenshots, report, evidence,
review and SHA-256 manifest. Open `presentation.html` after extracting it. The video
is a short silent backup, not a five-minute narrated presentation.

The package excludes uploads, user databases, cookies, keys and facilitator material.
The rehearsal owner cookie is stored only in ignored verification output and never
included in the shareable ZIP. The browser recording exports a new local rehearsal
draft from an isolated workspace. Private user backups were not attempted while the
user's server remained running.

Evidence hashes unchanged:

- Bundle: `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`.
- Replay supplement: `3f3092bf6e8ba1d965ca275e3581082c0ee90a38ab44a5c5ee9e460201cd1166`.

Logs and receipts are in ignored `output/judging-20261012/`. The reviewed source ZIP
is a separate code backup; it does not include installed dependencies or constitute
an offline installation.

## AI claims and remaining team actions

No additional paid calls were purchased. The preceding four-request evaluation cost
approximately **$0.0157780** nominally and exhausted its authorized campaign budget.
Its exact final passing response retains one tentative explanation and one check;
older failing/comparison captures retain a check while explanations are omitted.
Read-only inspection also found a user-generated post-restart v20 comparison at
11:31:21 CDT with **zero hypotheses, one check and no fallback**. That successful
saved question-only result is useful as a limited example, not evidence of reliable
explanations across every context. The exact captures and 57 mocked contexts remain
regressions; they do not establish measured engineer benefit.

Keep optional AI out of the critical demonstration path. Use recorded analysis,
stored replay and exports; preload any saved deep example before the talk. The
running user API needs a deliberate restart to load this closeout's backend changes.
Existing saved answers remain accessible/historical; they are not silently regenerated.

The team must confirm registration and acceptance of travel details (the supplied
email's 7 October deadline has passed), presentation/Q&A duration, rubric and local
start time/room. Rehearse on the actual laptop/projector/adapter with Wi-Fi off,
finish the presentation deck, copy the extracted offline package to another device,
and stop the app before making/verifying a private backup. Publish the reviewed
local commit and require both remote verification jobs to pass. No organizer
message, registration, booking, push or public deployment was performed.
