# Evidence-backed AI investigation

Status: COMPLETE
Baseline: 168e1de71334510dc92539ea78580f72aaec35a7. Working tree clean at start.
Commit posture: leave implementation uncommitted; no push or deployment requested.
Assurance: Guarded. Cloud tools handle derived experiment data and must preserve consent, scope, immutable verdicts, and evidence provenance.

## Scope

1. Read-only tools for model metrics, required fault cases, comparison, and stored warning events. Model-selected conclusions must resolve to server-verified claims and source identifiers.
2. Bounded tool-calling workflow with request/token limits, cancellation, timeout, and evidence fallback. No training, holdout scoring, arbitrary queries, or writes available to AI.
3. Data setup review using local validation and suggested mappings. No raw rows, headers, file paths, equipment IDs, or contact details sent to the provider. Applying a suggestion only edits the draft mapping.
4. Compact assessments and source links in existing analysis UI, reusable review briefs, and visible tool provenance.

## Verification

- Tests at tool, provider, API, and browser seams, including untrusted arguments, inaccessible evidence, missing data, consent/revocation, timeout/cancellation, and fallback.
- Mock all cloud calls during routine checks. Do not read or print secrets. Report live evaluation as unavailable if a server-side key is absent.
- Python focused tests and lint, TypeScript check/production build, relevant browser workflows, desktop/mobile visual check in both themes.
- Review both feature completeness and security/evidence boundaries before the final verification gate.

## Implementation state

Implemented read-only model/fault/comparison/warning tools and local dataset review. The provider can select only server-authored claims and references. Added scoped consent, a bounded investigation loop, local fallback, exact-case citation links, editable mapping drafts, reusable review briefs and portable audit exports.

Closeout: 104 non-integration backend tests, 29 browser regressions, TypeScript/production build and Ruff passed. The sample training/freeze/validation/export browser test passed separately. Desktop/mobile visual checks passed in both themes. Reviewed scope isolation, provider packet privacy, claim-source resolution, public storage quotas and historical coverage behavior. No live provider calls were made. See TESTING.md for evidence and limits.
