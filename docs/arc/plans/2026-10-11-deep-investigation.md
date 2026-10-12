# Saved deep investigation

Status: DONE. Planned/effective assurance: Guarded (cloud admission, consent, provenance and model-generated interpretations). Single owner at the user's request. Source remains uncommitted and undeployed.

Baseline: HEAD 3b0d54c951634e09bbe64731635d1f4bc3e6742b plus the reviewed, uncommitted routine-local cleanup. Preserve those changes. No real storage, secrets, datasets or recorded evidence changes; no paid calls, training, deployment or commit.

Seams: explicit `deep` request only; structured qualitative synthesis over server-computed, aliased fault patterns; optional result contract for historical compatibility; existing saved-job, consent, cancellation and brief conversion lifecycle. One or two recorded models within one partition. Replay and dataset review remain local.

<task id="deep-contract" kind="behavior" status="done">
<intent>Compute fault patterns locally and produce a cited report with tentative explanations, alternatives, gaps and discriminating next tests through one bounded structured provider request.</intent>
<verify>.venv/Scripts/python.exe -m pytest tests/test_deep_investigation.py tests/test_routine_analysis.py -q</verify>
<done>Routine requests stay free; deep requests require permission; citations, scope, limits, reuse, revocation and conversion are verified with mocked providers.</done>
</task>
<task id="deep-ui" kind="behavior" status="done" depends_on="deep-contract">
<intent>Add a deliberate Deep investigation action and readable saved report using existing themed controls, loading state and brief editor.</intent>
<verify>npm run lint; npm run typecheck; npm run build; relevant fixture browser suites</verify>
<done>Permission and failure states work, output waits for completion, saved report reopens and converts without another model request, desktop/mobile and themes work.</done>
</task>
<task id="closeout" kind="verification" status="done" depends_on="deep-ui">
<intent>Review privacy, correctness, report usefulness and compatibility; run fresh offline gates and document actual results.</intent>
<verify>Ruff, backend offline suite, generated types, frontend lint/types/protocol/build and assistant browser tests.</verify>
<done>Resolved findings and exact test results recorded. No unproven live usefulness claims.</done>
</task>

## Decisions and reviews

Deep investigation is an explicit local-workspace action for one or two recorded models in one partition. Hosted demo and replay do not admit new deep generation. Existing historical access remains guarded. A maximum of 24 prioritized patterns is sent, with omission disclosed. The server owns observations, numbers, verdicts and links; model text is separately labelled tentative, requires valid citations and competing explanations, and cannot add numbers, URLs or approval claims. These syntactic checks do not prove semantic entailment or causal truth.

Reuse includes completed deep reports and an active deep job when switching to a brief. Saved reports survive restart and removal of the provider key. Model/prompt changes make them historical without automatically paying for a replacement. Regular brief creation prefers an eligible saved deep report for the same models and partition. Conversion, serialized draft saves, export and all-owner revocation retain the existing storage/provenance rules. Failure falls back explicitly to local evidence; Retry and Cancel remain deliberate.

Long generated briefs use a compact leading explanation and priority test if the complete draft would exceed the existing 12,000-character save contract. No hypothesis or test text is truncated; the complete report remains stored and exported. An additional boundary test covers this final review fix.

Completion, correctness/privacy and Arc layout/accessibility reviews were performed locally without agents. Reviewed input privacy, immutable evidence, bounds, exact ordered contexts, owner/access checks, active-job reuse, historical currency, revocation tombstones, editable draft provenance, portable exports, keyboard disclosure/focus return and both themes at 390/1280 px. Existing components and tokens were reused. No new dependencies or database migration. Actual model usefulness and engineer decisions remain unmeasured because verification was offline.

Two test issues were repaired without weakening assertions: the new browser fixture now intercepts child review/save URLs, and the existing animation test fetches the real selection response before releasing its entrance-animation gate so network latency cannot consume its observation window. A concurrent fixture-startup attempt hit the existing 30-second limit; a subsequent ordinary-config run after the backend gate started normally and passed. No application animation source was changed.

## Closeout, 11 October 2026

- Ruff across backend/app, tests and scripts: passed.
- Final full offline backend gate: **284 passed**, one native Windows symlink permission skip, three integration tests deselected (51.62 seconds). Includes 16 new deep tests and 17 routine admission tests. Provider responses are mocked; no training or paid calls. The earlier 283-case gate also passed on the loaded host; the final gate includes the brief-size safeguard.
- Generated types exactly match a fresh generator output.
- Frontend lint, TypeScript, seven protocol tests and production build: passed. Existing bundle-size advisory remains.
- Broad 45-case browser run: 40 passed; four new fixture-routing failures and one network-timing animation failure. After corrections, **all nine affected deep/motion checks passed** in a fresh run (27.9 seconds). Together the runs verify all 45 relevant cases; no failed assertion was removed. Existing recovery, investigation, workspace permission and UI suites passed in the broad run.
- Twelve offline routine evaluation cases passed, with zero provider requests, unchanged evidence and no training jobs.
- Receipt: ignored `output/deep-investigation-verification.json`; source hashes exclude plan/index metadata. Existing routine-local baseline changes remain included and preserved.

## Authorized live repair, 11 October 2026

The user subsequently authorized five paid requests to diagnose repeated verification failures. Exactly five requests were admitted, with no retries; estimated token charges total $0.0123196. This authorization supersedes the original offline-only scope for this bounded diagnostic run. No subagents were used. Local reviews covered privacy/admission, provider-only versus stored contract compatibility, hypothesis framing, contextual approval rejection, the narrow simulated-dropout exemption, immutable evidence and captured-response regression coverage.

The original recommended aug3 report completed live with prompt v7 in 5.31 seconds and retained its saved identity through reopen and brief conversion. The fifth response for failing lr2 identified the final false causal-wording rejection; that exact response and aug3 then passed final code through API/save/reopen/conversion using offline capture replay. No sixth paid call was made. Real provider text is now framed by the server instead of requiring magic tentative words; the provider no longer writes the summary or verdict. Actual fault shortfalls, protocol boundaries and metric definitions are supplied without inventing missing settings.

Fresh closeout: 124 relevant backend tests, targeted Ruff and exact generated types passed. Four real-response UI checks passed (aug3/lr2 at dark 1280 px and light 390 px), including visible evidence, retained brief content and no error/overflow. Assistant routes were intercepted for these UI checks, with zero paid calls or user-data mutations. Two captured qualitative responses form offline CI regression fixtures. No frontend source changes, migration, training, reserved scoring, commit or deployment. Receipt: `output/deep-live-repair-20261011/verification.json`. Provider success is observed; causal truth and improved engineer decisions remain separate evaluation work.

## Authorized comparison repair, 11 October 2026

The user separately authorized a maximum of four paid requests for the aug3/lr2 comparison. Exactly four were used, with no retries; estimated token cost $0.0103096. The second request reproduced the actual failure: valid numbered hypothesis references triggered the numeric-claim ban. Prompt v8 prefers explanation titles; verification permits only references to hypotheses actually present in the same report, retaining measurement, unknown-reference and approval safeguards.

The packet also contained only lr2 fault patterns because global failure-first selection exhausted the bound before reaching aug3. Bounded selection now reserves evidence for each model, ranks the chosen subset by recorded failures, spills unused capacity without invention, and records per-model available/provided counts. Single-model ordering, aliases, immutable metrics, public types and storage remain unchanged. Reviewed deterministic selection, exact source attribution, missing-model evidence, input budget, hypothesis-index boundaries, historical fingerprinting and one-request lifecycle locally; no agents were used.

The final two requests completed live in both candidate orders with 12 patterns per model, unchanged evidence, saved-report reopen and brief conversion (5.56/5.20 seconds). Exact captured packets and responses are offline CI fixtures. The rejected response is replayed only for validation in its original citation scope. Fresh gate: 136 relevant backend tests, broad Ruff and exact generated types passed. Four intercepted browser checks passed through selection, local comparison, deep report, expanded evidence and brief conversion at 1280 px dark / 390 px light. Browser fixture capability/GET mistakes were corrected before the passing run; zero extra provider calls or user-record changes. Receipt: `output/deep-comparison-repair-20261011/verification.json`. Frontend source/build unchanged; no training, reserved scoring, migration, commit or deployment. Restart the ordinary API process to load the backend repair. Engineer usefulness and semantic entailment remain separate evaluations.
