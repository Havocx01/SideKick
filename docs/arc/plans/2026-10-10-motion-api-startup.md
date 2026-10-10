# Default motion and stable local API startup

Status: DONE. Single owner; no subagents. Uncommitted and undeployed.

User request: enable animations by default and repair the first-start shutdown from `tasks.ps1 api`.

Baseline: clean worktree at `9cf4ce7`. Preserve saved experiments, evidence and environment files. No training, validation or provider calls.

## Findings and changes

- Unset motion preferences inherited system reduced motion. Default to animations on; retain explicit saved off choices, keyboard operation and app-wide consistency.
- `tasks.ps1 api` always enabled Uvicorn reload. The installed Windows reload supervisor sends console Ctrl+C during restarts. The supplied log ends with orderly server and supervisor shutdown, consistent with a stop signal; it does not identify the sender. Remove the reload supervisor from normal launches, retain explicit `-Reload` watching only backend, align `make api`, and run from the repository directory. Do not claim a reproduced crash or silently restart after intentional stops.
- Add a port option for isolated entry-point verification and retain visible nonzero startup errors.

## Acceptance

- New browser contexts animate under both OS preferences; explicit off remains static and persists across refresh. Verify real rolling numbers, growing bars, canvas and border beam.
- Run the actual PowerShell task from another directory using a temporary workspace and unused port. Check repeated health/list requests past the reported shutdown interval, one server process, no reloader, then explicit scoped shutdown.
- Verify launcher tests, Ruff, frontend lint, TypeScript, production build, affected browser suites and protocol tests. Review the final diff locally. Leave changes uncommitted and undeployed.

## Verification and local review

- Ruff, TypeScript, production build and all 7 protocol tests passed. The existing large-chunk advisory remains.
- Launcher and real Windows entry-point suite: 15 passed in 44.51 seconds. Both PowerShell 7 and Windows PowerShell 5 stayed available with a single server for 12 seconds after readiness; occupied-port failures were visible, and the original fixture server remained healthy. Both shut down cleanly on explicit scoped Ctrl+Break. The user's existing server was not interrupted.
- Affected browser gate: 15 analysis/UI checks passed in the first run; the corrected motion/walkthrough files then passed all 15 tests in 40.9 seconds. The initial gate exposed test-only issues: seeding a saved off preference on every refresh, and checking mobile entrance bounds before movement settled. Corrected initialization and eventual exact bounds retain behavior assertions. No product motion was disabled to satisfy tests.
- Local completion review: default on under both system settings, persistent opt-out, API default without supervisor, explicit backend-only reload, absolute startup working directory, error propagation and preserved data/evidence all checked. Correctness review: no automatic restart, provider call, training, broader process stop or public/API/storage change introduced.
- Frontend lint passed again sequentially after browser completion; a concurrent repeat had raced Playwright recreating `test-results`. Final diff/whitespace checks passed. Verification receipt: ignored `output/motion-startup-verification.json`.

The original shutdown signal's sender remains unknown from the supplied log. Runtime verification establishes the new launch behavior, not a reproduction of that original external signal.
