# Minimal paid deep-investigation verification — 12 October 2026

Against HEAD `556fc2b72d2d0cf89183adfc08d29b15ab62990c`; preceding uncommitted
release and trace-explanation work is preserved. Single owner, no subagents.

## Result and changes

Four paid requests reproduced the screenshot's problem and exercised passing,
failing and comparison contexts. The final passing-model answer now verifies with
one tentative explanation, a distinct alternative and one trace-specific question.
The exact original provider capture is a regression fixture, not a rewritten answer.

Fixed three reproduced defects:

- Exact, directly cited server observation IDs in prose were incorrectly treated as
  invented numbers. Only validated citations in that item may bypass this numerical
  guard; uncited identifiers, numerical claims and links remain rejected.
- The prompt's generic dropout example encouraged the same explanation despite
  incompatible traces. Prompt `sidekick-deep-v20` supplies one compatible selected
  history, its recorded trace condition and exact citations. Retained warnings receive
  a separate condition; hypotheses cannot describe them as absent warnings.
- An available passing-model trace could distract from a failing comparison model
  whose trace was unavailable. Selection now prioritizes failed patterns and abstains
  from a trace anchor if no suitable failing history exists.

For directly cited histories retaining warnings, server-composed guidance compares
crossing timing, prior warning state and warning onset/lead with fixed recorded rules.
It rejects a question whose absent-warning premise the supplied records already
refute. This guidance is deterministic product value, not credited as AI-created prose.

Public types, stored reports, evidence, verdicts, consent, source scopes and result
links remain unchanged. Routine analysis remains local. Paid deep investigation still
uses one structured request, with no automatic provider retries. Historical answers
remain readable without automatically buying replacements.

## Paid ledger

Model: `gpt-4.1-mini-2025-04-14`. Four-request / $0.10 conservative admission cap;
durable ledger counts failed calls and prevents raising this campaign's limits.
No requests were made after the fourth call.

| Call | Prompt | Input / output tokens | Generation latency | Estimated cost | Current offline admission of exact capture |
|---|---|---|---|---|---|
| Passing aug3, initial | v19 | 8,837 / 231 | 4.26 s | $0.0039044 | Refuted below-threshold/absent-warning question rejected; evidence fallback |
| Failing lr2 | v19 | 8,902 / 244 | 4.53 s | $0.0039512 | Contradictory mixed-history explanation omitted; one valid question retained |
| aug3 versus lr2 | v19 | 8,967 / 233 | 3.29 s | $0.0039596 | Explanation contradicting recorded crossings omitted; one valid question retained |
| Passing aug3, after prompt fix | v20 | 8,979 / 232 | 4.28 s | $0.0039628 | One tentative explanation/alternative and one timing question retained |

Total estimated nominal cost: **$0.0157780**, approximately 1.6 cents, before any
cache discount. This is token-based estimation, not an invoice. The last call preceded
the targeted citation/scope admission repair; its untouched response was replayed
through the final code and API lifecycle without another purchase. Fresh v20 failing
and comparison generations were **not** made after exhausting the four-call budget.

Original ledger and packet/answer receipts:
`output/deep-evaluations/deep-live-20261012/`. Four unchanged regression fixtures
are in `tests/fixtures/deep_paid_*_20261012.json`; their hashes match the originals.
Final local-versus-captured review:
`output/deep-evaluations/deep-live-20261012/final-offline-review/`.

## Verification

- Full non-integration backend gate: **434 passed, 1 skipped, 3 integration checks
  deselected**. No training, AI or reserved-validation jobs launched by this gate.
- Offline matrix: **57 mocked generations** covering all 10 recorded configurations,
  all 45 unordered model pairs, an upload-shaped context with engineer notes, and
  missing replay evidence. One dispatch per context, source/partition scope, immutable
  evidence and honest abstention verified. These are contract tests, not live samples.
- Exact final paid capture passed mocked API create → GET → reuse (same ID) → brief
  conversion → save → export with one provider dispatch. Exact failing/comparison
  captures and rejected initial passing response have independent regression tests.
- Browser deep, recovery and presentation suites: **42 passed**, covering 390 px
  and desktop layouts in both themes, direct-history facts, partial/abstained reports,
  deliberate permission, revoked/denied output, GET-only recovery, retained job IDs,
  context replacement and draft revisions during saving. Final receipt:
  `output/deep-evaluations/deep-live-20261012/browser-verification.log`.
- Ruff, frontend lint, TypeScript, production build and **7 protocol checks** passed.
  Generated frontend API types have the same hash as the generator's output.
  Existing Vite large-chunk advisory remains.
- Evidence SHA-256 unchanged: bundle
  `f416963e03a22f694f8167179b21bc671733cf809cff4508ce228d576c7cf8f6`;
  replay supplement
  `3f3092bf6e8ba1d965ca275e3581082c0ee90a38ab44a5c5ee9e460201cd1166`.

## Limits and running application

The final passing answer offers a more specific question about retained-warning
timing and a tentative explanation. The failing/comparison captures still provide
weak explanations, which are omitted safely. Consistent superiority over regular
analysis, faster engineer decisions and real-equipment reliability remain unproved.
No human participant study was conducted. Readable output is not a semantic proof of
every sentence, a physical-cause diagnosis or deployment approval.

The user's API on port 8140 was started before the latest changes with reload
disabled. It was not stopped or modified. Restart with Ctrl+C followed by
`.\tasks.ps1 api` to load the fixes. Saved output is not automatically regenerated;
an explicit Retry may buy a new answer under the usual permission and admission rules.

No user database edits, new training, commits, pushes or deployment. Docker was
previously checked in the separate release receipt; it was not repeated for this
provider-only change.

### Screenshot follow-up

After the user reported another failure, read-only inspection found the current API
started at **11:26:25 CDT**, after both updated backend files. The matching saved
claims-verification failure was created at **11:25:48 CDT**; another generic
verification failure was created at **11:26:04 CDT**. Neither is a post-restart
generation. No newer deep record existed at follow-up inspection. Thus the screenshot
does not establish a new-generation failure in the restarted backend, but neither
does the passing captured regression establish reliable live success there.
Reopening a saved failed analysis preserves it rather than launching another paid
request. No extra provider requests or user-store edits were made in this follow-up.
