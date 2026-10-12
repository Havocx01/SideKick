# Minimal live deep-investigation verification

Status: DONE. Single owner; no subagents. All preceding dirty work preserved.

User explicitly authorizes paid testing across deep investigation with minimal spend.
Task ceiling: four provider requests total, $0.10 conservative admission ceiling,
current configured model, no provider retries. Durable separate campaign ledger;
failed requests count. Historical records and user server remain untouched.

1. Test screenshot's passing model first, then failing model and comparison.
2. Inspect exact provider packets and retained/rejected sections; repair reproduced
   failures offline rather than spending on repetition. Reserve fourth call only for
   necessary verification after a provider-path fix.
3. Verify remaining candidate families, missing records, uploaded context, consent,
   saved reuse, brief/export, scopes and UI with offline fixtures and relevant tests.
4. Record retained explanations, actionable questions, scope and cost honestly.
   Green contracts do not establish superiority to regular analysis or field reliability.

Completion: four requests, estimated $0.0157780. Final exact passing response retains
one tentative explanation and one trace-specific check. Failing/comparison captures
retain valid questions while contradictory explanations are omitted. No fresh v20
failing/comparison purchase after the fourth call. All 10 configurations and 45 pairs,
uploaded context and missing evidence covered by 57 mocked generations. Backend gate
434 passed / 1 skipped / 3 integration deselected; 42 browser / 7 protocol checks,
Ruff, lint, generated types and TypeScript/build pass. Evidence unchanged.

Receipt: [Paid verification and limitations](../audits/2026-10-12-deep-live-verification.md).
The running user API predates these changes and requires an explicit restart.
Changes remain uncommitted and undeployed; consistent engineer added value is unproved.
