# Sidekick reliability completion review

Target: `046a97240e852c8818d5da6baaccd5a4e5a88cae` plus the preserved remediation and current reliability changes, including non-ignored new files. Initial and final source manifests are under ignored `output/remediation/`. Changes remain uncommitted and undeployed.

## Whole-implementation review

Independent spec and standards/privacy reviewers inspected the same worktree. They found two further actionable defects: a concurrent brief save could be overwritten by conversion, and a cloud-result record with a retained evidence-only brief lost conversion/export access after revocation. Both were reproduced offline without provider or training requests.

The fixes serialize client conversion with draft writes, guard conversion acknowledgements by draft revision, and merge current server draft fields inside a SQLite write transaction. Retained evidence-origin briefs can be converted/exported with reconstructed local evidence. Revoked record writes remain denied so late cloud autosaves cannot resurrect private text. New API/browser regressions cover both findings.

After fixes, the controller rechecked spec completion and standards/privacy locally against the regenerated target. The standards reviewer exhausted its available usage after providing its concrete reproduction; its unfinished final response is not counted as an approval. Local re-review inspected owner/scope/expiry checks, migration-before-upgrade provenance, atomic revocation/tombstones, conversion merge, draft revision/write ordering, response-only currency, active/historical reuse, fixed-path provider request count, server action ranking, capacity accounting and evidence/source guards. No remaining actionable defect was found in those reviewed seams. This is bounded code/fixture evidence, not certification of every interleaving or field usefulness.

The full browser run also exposed stale walkthrough assumptions: transitional Cult previews briefly coexist in the DOM, and sensor faults are intentionally always expanded. The replay assertion also uses the current guided “Warning on/off” copy, checking both original and faulted stored states. Tests now select only the present, accessible preview (excluding the aria-hidden outgoing preview), use the compact heading and threshold-bearing chart label, and assert the expanded matrix, retaining the exact warning counts, read-only behavior and keyboard scoring disclosures. These test-only repairs were re-reviewed locally on both completion and standards axes before the final gate.

## Bounded live check

One authorized failing-result analysis used the unchanged configured `gpt-4.1-mini-2025-04-14`, retry count zero, a six-request ceiling and conservative $0.10 budget. It completed in 7.84 seconds with five requests and estimated usage cost $0.0024564. All essential facts and the specific dropout check were retained: missing-reading flags, median imputation, late and missed warnings. Evidence hashes were unchanged and no experiment jobs were created. Full outputs and meter: ignored `output/reliability-live-check/`.

The comparison with local output still showed equivalent essential information in this case. A successful, safe result does not demonstrate better engineer decisions. Fixed comparison/warning/data paths are verified with mocked provider responses to use exactly one structured selection request after server inspection; the full paid suite was not repeated.

## Closeout gate

Fresh final results: 199 backend tests, 65 browser tests, 7 protocol tests and 12 offline assistant cases pass; Ruff, lint, TypeScript, generated types and production build pass. The isolated synthetic train/freeze/validation/export checks pass in both backend and browser gates. Exact commands are recorded in TESTING.md and the plan ledger. Reviewed source target SHA256: `2b78bd9c02eb06afd2c6280003d81df41027974edcf03f9a9b40a6c55b24d8c2` across 73 files, unchanged through the final gate; plan/audit/verification metadata is excluded. Docker runtime requires the unavailable Docker Desktop Linux engine; configuration-only loopback checks are distinct. Real-equipment reliability and the counterbalanced engineer study remain separate milestones.
