# Prepare an engineer evaluation packet

This is a preparation tool, **not a completed engineer study**. It makes a local,
printable packet from Sidekick's committed historical evidence and synthetic CSV
fixtures. It launches no training, reserved validation or provider requests and
does not read your uploads, assistant database, `.env` or API keys.

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/prepare_engineer_evaluation.py --output output/engineer-evaluation
```

Use a new directory for each packet. The command refuses to overwrite an
existing packet or a reviewer's observations. `--bundle` optionally chooses a
different recorded bundle; the default is `evidence/bundle.json`. That bundle
must contain two qualifying configurations, a failing configuration whose
decisive fault is dropout below the detection minimum, and a replay with an
inactive point before its first active warning and before the useful warning
window. The early-alarm maximum must be at most 95% so the five-percentage-point
failure fixture is possible. Unsupported bundles are rejected before output
is created rather than paired with an incorrect answer key. Output stays under the
ignored `output/` directory by default.

The packet contains:

| File | Recipient and purpose |
| --- | --- |
| `reviewer/manual.html` | Raw scoped server references, protocol/file context, limits and a decision worksheet. |
| `reviewer/local.html` | The same contexts with actual deterministic analysis and available brief examples. |
| `reviewer/evidence/*.csv` | Complete synthetic CSVs for the data-review cases; these are not registrations in the running app. |
| `facilitator/answer-key.html` | Essential server facts and proposed next-check criteria. Keep separate from reviewer materials. |
| `facilitator/answer-key.json` | Machine-readable facts, reference IDs, local actions, scope and limitations. |
| `facilitator/cases.json` | Exact request contexts, sources, evidence digests and deterministic outputs. |
| `score-sheet.csv` | Blank observations for manual, local and AI methods; unavailable AI rows are explicitly marked. |
| `method-order.csv` | Three counterbalanced method orders for independent reviewer cohorts. |
| `manifest.json` | Bundle SHA-256, preserved recorded identifiers, version, case count and generated-file hashes. |

Open the HTML files locally in a browser or print them. They are self-contained:
no remote fonts, scripts, analytics or network assets are needed. The printable
packet uses Sidekick's blue accent and restrained typography. JSON and CSV retain
full identifiers and long labels even when a printed page needs more space.

## Cases

The twelve cases cover a qualifying result, detection failure, pass/fail
comparison, two qualifying configurations, active and inactive replay points,
an unavailable cycle, excessive early alarms, ready CSV data, unconfirmed
failure labels, missing sensor readings and duplicate equipment/cycle pairs.

The excessive-alarm case is explicitly a **private copied protocol fixture**:
healthy early-alarm burden is set five percentage points above the recorded
limit, and qualification is false. It is not a measured historical result or a
retrained model. All four CSV cases use seed `20260918`, 30 simulated histories
and 100–160 operating cycles. Their readiness and problems are computed through
the existing data-validation and deterministic-analysis paths.

Recorded source/configuration identifiers are retained exactly. Historical
missing identifiers stay `null`; the generator adds the actual bundle SHA-256
rather than inventing a source fingerprint. Synthetic contexts and changed
fixtures have their own scoped analysis digests. No changed fixture is written
back to the committed evidence bundle.

## Conduct the review

Follow [the engineer evaluation protocol](sidekick-engineer-evaluation.md) to
agree the decision, success criteria and study conditions before scoring. Have
an engineer adjudicate the facilitator rubric first. The suggested next checks
are grounded in verified server facts; they are not an AI answer used as its
own reference. Actual local next checks remain separate so weak actions can be
identified rather than automatically awarded a good score.

Give reviewers only their assigned case/method material. This packet deliberately
reuses the same contexts for parity; do not show one person an identical case
under all three methods in one session. Use independent reviewers or separately
adjudicated equivalent cases, record prior familiarity, and treat a single
engineer's results as exploratory. Counterbalancing alone does not remove
learning effects.

Record review time separately from generation waiting time, critical scope
mistakes, essential facts missed, concrete next checks, brief edits and a reason
for any helpfulness rating. Blank cells mean unobserved, not zero. Report
failures, abstentions, exclusions and fallback separately.

**AI outputs are absent.** The script has no live mode and does not substitute
deterministic text for AI. AI rows remain `not_available` until separately
authorized saved output is matched to the packet's exact context and evidence
identity. No model usefulness, time saving, reliability or field performance
claim is produced by generating this packet.
