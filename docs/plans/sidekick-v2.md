# Sidekick V2 implementation

Approved scope: contextual investigation, two-model comparison, replay explanation and editable review briefs. Beautiful UI task rows, insight/context cards, tool chips, selection actions and consent cards are the visual reference. Preserve Sidekick tokens and compact navigation.

## Authority and baseline

- Branch: codex/sidekick-v2; starting HEAD fdb066d4eda210e117e93b485538bbcaea627461.
- Earlier uncommitted changes are from this conversation and are retained. Initial fingerprints: output/v2/baseline.json.
- No commit, push, deployment or purchase authorized. Implementation remains local.
- Planned/effective assurance: guarded, because derived equipment data can leave the machine and provider calls incur usage.
- The optional Arc workflow bundle lacks its supporting references. Use the approved plan and existing repository checks; do not block implementation on optional tooling.

## Seams and slices

1. Evidence engine: exact experiment/configuration/partition/scenario references, four deterministic workflows, structured OpenAI selection of verified findings; unit tests.
2. Access and lifecycle: server credentials, private-demo unlock, experiment consent, SQLite records, quotas, cancellation, interruption, exports; API tests.
3. Interface: replace permanent guide with contextual inspector, compare selection, replay action, editable brief, Beautiful UI patterns; browser tests and visual review.
4. Integration and release: generated contracts, docs, 2.0.0 identifiers, spec/security review, fresh backend/frontend verification.

## Agreed contract

Public types: backend/app/assistant/schemas.py. POST /api/assistant/analyses returns AnalysisRecord; GET /api/assistant/analyses/{id} polls; POST .../{id}/cancel cancels. GET /api/assistant/capabilities?experiment_id=...; GET/POST /api/assistant/consent/{experiment_id}; POST /api/assistant/access; POST .../{id}/brief accepts BriefUpdate; GET .../{id}/export downloads ZIP. All frontend requests use X-Sidekick-Request: 1.

Evidence builder: build_analysis(bundle, AnalysisRequest) -> AnalysisResult, raises ValueError for invalid/unavailable context. Provider: async enhance_analysis(result, context, settings) -> AnalysisResult. Service owns status transitions, timeout/fallback/access and never lets provider output supply numbers or URLs.

## Implementation state

- Evidence engine: complete; display values, source context, deep links, separate detection/burden cases, comparison overview, replay fallbacks and brief drafts
- Access and lifecycle: complete; public evidence allowance returns HTTP 429; workflows gated by SIDEKICK_ASSISTANT_TASKS
- Interface: complete; Evidence guide removed; inspector shows comparison table, labelled AI interpretation, evidence-query chips and prefilled brief
- Provider: verified interpretation (aliases only; no numbers, links, cause/deployment claims or contradictory verdicts); prompt sidekick-analysis-v2.2
- Integration/review: complete locally; types regenerated, 2.0.0 identifiers applied, Beautiful UI MIT notice retained. A dedicated security review has not been run.
- Closeout: 81 backend and 13 browser tests, TypeScript, build and Ruff pass (TESTING.md). Nothing committed or deployed.
- Engineer usability study (three to five engineers versus V1.5): not run.
- Live evaluation: pending credentials; do not expose secret values in logs or tooling.

## Defaults

OpenAI gpt-4.1-mini-2025-04-14; server-side key; 45-second timeout; 8000 input and 1200 output tokens; no SDK retries; one live generation; ten requests per presenter session and 25 per day. Full mode permits local configured live analysis; demo requires presenter unlock; replay is always evidence-only. Uploaded results require per-experiment revocable consent. No raw readings, filenames, contact information or physical-cause/deployment claims.

Public demo results expire with their owning session/experiment. Free-host quotas do not promise a durable monthly billing cap. Do not change historical bundles or trigger training/holdout from assistant tools.
