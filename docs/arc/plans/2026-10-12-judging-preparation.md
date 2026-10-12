# Judging preparation

Status: DONE. Single owner, no subagents. Planned/effective assurance: Standard
for presentation artifacts and checks; preserve existing evidence/privacy boundaries.
Full Arc reference bundle unavailable; use the repository's scoped sequential workflow.

## Implementation state

Baseline HEAD: `556fc2b72d2d0cf89183adfc08d29b15ab62990c`. Existing dirty changes
are previous authorized work from this chat and are preserved; their SHA-256 baseline
is in ignored `output/judging-20261012/baseline.json`. New scope: `SUBMISSION.md`,
stale README walkthrough text, `docs/judging-guide.md`, this plan and audit/index,
`backend/app/assistant/service.py` and a focused contract regression in
`tests/test_deep_evidence_inputs.py`. Exclude generated Playwright artifacts from
`frontend/eslint.config.mjs` to avoid a lint/browser cleanup race. Ignored demo media, exports and receipts under
`output/judging-20261012/`. User experiments and the port-8140 server stay untouched.
Final wording review also makes retained-warning guidance conditional on the clean
counterpart's recorded state, with a focused regression in `tests/test_trace_reasoning.py`.

Commit posture: prepare a reviewed local commit under the user's existing commit
authorization and current instruction to finish preparation. No push or deployment
without explicit publishing authorization. No additional paid AI; prior four-call
evaluation budget exhausted. Synthetic integration jobs use disposable stores only.

<task id="currency" kind="behavior" status="done">
<intent>Include trace-admission rules in output currency without purchasing replacement output.</intent>
<verify>Focused saved-record/API regression, then full backend gate.</verify>
<done>Changed trace contract marks saved output historical; GET/reuse does not buy a new answer.</done>
</task>
<task id="materials" kind="artifact" status="done">
<intent>Current V2 handoff, five-minute/two-minute script, concrete claim limits and offline backup media/report.</intent>
<verify>Actual recorded metrics/routes; fresh browser recording with external traffic blocked and no paid AI.</verify>
<done>Artifact paths are usable; historical, synthetic and captured AI evidence are honestly labelled.</done>
</task>
<task id="gate" kind="verification" status="done">
<intent>Final local gate, isolated cold launch/restart and packaged runtime, exact remote status and reviewed local commit.</intent>
<verify>Ruff, pytest including synthetic integration, generated types, lint/typecheck/protocol/build, full browser suite; isolated Docker/checks.</verify>
<done>Record actual results and prerequisites. Remote CI remains separate from local success. Provide user registration, organizer, rehearsal and backup tasks.</done>
</task>

## Event context

User-provided organizer email: own laptops/materials; individual registration;
Monday arrival, Tuesday 09:00 team start, Wednesday awards; travel details requested
by 7 October. No presentation duration or rubric supplied. Official event home lists
12–15 October 2026; public agenda does not expose a finalist judging duration.
Do not assume another conference session is the team's judging slot or send messages
to the organizer. Prepare adjustable material and leave schedule confirmation to user.

## Closeout

439 backend / 105 browser / 7 protocol checks passed; Ruff, generated types,
lint/TypeScript/build and fresh Docker synthetic runtime passed. Cold API start and
restart retained saved brief/export. Current guide and 14-file portable demo package
prepared and inspected. No paid calls, user data edits, push or deployment.
Reviewed local commit is the authorized final checkpoint; identification is in the
ignored release manifest/Git history. Remote CI and physical rehearsal remain team
actions, not unperformed local implementation work.

Receipt: [Judging readiness](../audits/2026-10-12-judging-readiness.md).
