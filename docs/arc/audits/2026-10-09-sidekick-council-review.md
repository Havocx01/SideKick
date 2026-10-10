# Sidekick: full council review

Date: 2026-10-09  
Baseline: `046a972`, clean working tree at review start  
Scope: React frontend, Python backend, evidence workflow, AI assistant, experiment library, tests, build and deployment configuration  
Stage: engineering prototype with a public demo; inferred from implementation and project documents, not separately confirmed by the owner  
Method: three independent Codex council members, anonymized peer review, chair verification, mechanical checks, and representative browser inspection. No external model API was used for the council.

## Verdict

Sidekick has a useful core: it helps an engineer compare warning models, inspect their sensitivity to sensor faults, and retain the evidence behind a review decision. Its strongest feature is the relationship between protocol, results, replay, and a reproducible frozen model. The current UI communicates that relationship much better than a generic model dashboard would.

The next investment should be reliability and independent-data checks. The documented build workflow currently breaks, the test gate is red, and accepted inputs can either make training fail or undermine the independence of development results. More visual effects or a more capable language model would not address those problems.

The app is suitable for demonstrating and developing the workflow. This review does not establish readiness for operational equipment decisions or field deployment. Whether it improves an engineer's actual work remains a question for a small, bounded pilot.

## What is working well

- **Evidence integrity has real implementation behind it.** Preprocessing is fitted on training histories; equipment groups are separated by ID; threshold selection uses development predictions. The review found no evidence that reserved predictions are used to fit the recommendation.
- **Freeze and validation preserve an auditable record.** The model, threshold, protocol, source, split and artifact identifiers are captured. Serialized predictions are checked, and the exposure ledger records use before scoring so cancellation or interruption cannot make used histories appear fresh again. See `backend/app/experiments/validation.py` and `backend/app/experiments/exposure.py`.
- **AI is constrained to evidence.** The server supplies numbers, references, approved claims and scoped tools. The model cannot independently approve deployment or invent measured results. A deterministic analysis remains available without a provider. See `backend/app/assistant/investigation.py` and `backend/app/assistant/agent.py`.
- **Privacy and demo scope are deliberate.** Cloud input is derived, scoped evidence rather than raw CSV rows and user identifiers. Consent is scoped and revocable. Hosted demo ownership and restrictions are substantially different from local full mode, and the distinction is enforced in the backend.
- **The visual identity is coherent.** The compact library, restrained blue controls, distinct ready/completed states, Data and protocol diagrams, and contextual replay form a consistent Sidekick interface. The library and protocol overview were readable at desktop and 390 px mobile widths. Preserve this foundation.

## Verification results

| Check | Result | Meaning |
|---|---|---|
| Frontend `npm run build` | Passed | Current checked-in types compile; production assets build. |
| Fresh generated types, substituted in a read-only TypeScript compiler host | 26 diagnostics | Normal type generation removes the library interfaces and breaks compilation. No tracked file was overwritten during this check. |
| `pytest -q -m 'not integration'`, live assistant disabled | 129 passed, 1 deselected, 12 setup errors | All errors come from the pilot fixture omitting a now-required creation date. The suite is not green. |
| Frontend protocol unit tests | 7 passed | The focused protocol helpers passed. |
| Ruff over backend, tests and scripts | Passed | No reported Python lint violations. |
| `pip check` | Passed | Installed Python dependency requirements are compatible; this is not a vulnerability audit. |
| `npm audit --json` | 0 known vulnerabilities | No advisories reported for this lockfile at review time. |
| Safe tracked-text credential scan | 0 candidates | No credential-shaped matches in the scanned tracked text; local `.env` values were not printed or included. |
| Input probes without fitting | Three failure mechanisms reproduced | Duplicate identities cross partitions; one-class folds pass admission; long protocol crashes augmentation sampling. |
| Representative browser review | Library, protocol, comparison, analysis, replay and sample setup inspected | Isolated fixture workspace; light desktop/mobile and dark mobile library. No exhaustive browser-suite claim. |

The browser analysis was **recorded-evidence mode**, not paid live AI. No training, model fitting, reserved-validation job or paid AI request was launched. The temporary loopback server used a separate workspace and was stopped afterward. Application source files were not changed.

The full Playwright suite was not executed because it includes training flows. A source-verified stale assertion is recorded below. Python integration training coverage was excluded deliberately.

## Advisory scorecard

This is a prioritization aid, not a product-value score or a deployment certification. Scores use a simple 0–3 scale: 0 broken gate, 1 material gaps, 2 working foundation with gaps, 3 strong verified coverage. The installed audit skill's full scorecard/reference bundle was unavailable; these are chair-calibrated judgments rather than an official Arc grade.

| Area | Score | Basis |
|---|---:|---|
| Security posture | 1/3 | Good demo/privacy boundaries; local Docker full mode is published on all host interfaces. |
| Performance | 2/3 | Existing lazy page chunks; large initial bundle needs measurement and selective deferral. |
| Architecture | 2/3 | Useful domain separation and persisted evidence; some broad UI/service modules and generated-contract drift. |
| Code quality | 2/3 | Typed models, clean lint and explicit guards; admission checks do not cover every training precondition. |
| Test health | 1/3 | Substantial passing coverage, but 12 setup errors and browser interaction gaps. |
| Resilience | 2/3 | Persistent jobs, cancellation and deterministic fallback; analysis polling does not recover after a transient read failure. |
| Operations | 0/3 | The documented build path regenerates a broken type contract; CI also has failing tests. |
| **Core total** | **10/21** | Address build and data validity before extending scope. |
| Accessibility, separate | 2/3 | Good semantic controls and mobile layout; reduced-motion preference is explicitly overridden on the overview canvas. Full assistive-technology testing was not performed. |

## Codebase map

| Area | Main responsibilities |
|---|---|
| `backend/app/data`, `features`, `models`, `scoring`, `faults` | Input profiling, features, grouped model training and warning/fault evaluation. |
| `backend/app/experiments` | Uploads, persisted jobs/library, frozen models, exposure and final validation. |
| `backend/app/assistant` | Verified evidence tools, provider orchestration, saved analyses, briefs and consent. |
| `backend/app/api`, `schemas.py` | Mode/ownership guards and typed public interfaces. |
| `frontend/src/views`, `components` | Evidence pages, setup/progress, file-browser library and shared analysis UI. |
| `scripts/generate_types.py`, `tasks.ps1`, `.github/workflows/verify.yml` | Contract generation and local/CI verification paths. |

The review counted approximately 150 application files. Large files include the experiment view, schemas and shared stylesheet. Their size alone is not a defect. Extract a focused responsibility when changing those areas; a broad rewrite is not justified by this review.

## Prioritized findings

Four work groups contain **4 high, 6 medium and 4 low findings**. P1/high means address before relying on the affected workflow; P2/medium means correct a reachable failure or operational gap; P3/low is a bounded improvement. No critical exploit or data-loss incident was demonstrated.

### 1. Restore the build and verification gates

**F1 — P1/high: type generation removes the library contract.**

`scripts/generate_types.py:25` omits the library models from its roots. `frontend/src/api/types.ts:386` contains manually added `LibraryFolder`, `LibraryItemRef`, `LibraryItem`, `LibrarySnapshot` and `LibraryUpdate` definitions despite the file's generated-only header. The generator overwrites the entire output at `scripts/generate_types.py:147`.

`tasks.ps1:105` runs type generation before the frontend build. CI also generates and compares the types. A read-only regeneration comparison removed those library definitions; substituting that output into TypeScript produced 26 diagnostics, including missing imports in the API client and library. Thus a plain frontend build passes while the documented build path cannot reproduce it.

**Repair:** include all public library roots in generation, or move intentionally manual types to a separately owned file. Require clean generation, no diff and successful compilation together. This finding was discovered and verified by the chair after the council's peer round.

**F2 — P1/high: the pilot verification gate is currently unusable.**

All 12 pilot tests error during fixture setup: `tests/test_pilot_review.py:25` calls `Workspace.reserve` without `created_at`; `backend/app/experiments/store.py:102` indexes that field to register the run in the library. This is fixture drift, not evidence that actual pilot requests are broken. CI runs pytest and therefore cannot presently validate this area.

**Repair:** construct a valid fixture record, then run the pilot and ordinary backend gates. Avoid weakening the production record requirement merely to accommodate an invalid fixture.

Also update `frontend/tests/workflow.spec.ts:41`, which expects `.analysis-source` while the analysis now renders grouped context rows. This is a source-verified mismatch, not a claimed Playwright execution result. Add fixture-only browser coverage for inline rename, folder/context menus, selection, archive protection and dragging. Backend library coverage exists; the gap is browser interaction coverage. The frontend also lacks a lint script; add a proportionate check once the existing gates are healthy.

### 2. Check study independence and training feasibility before reservation

**F3 — P1/high: duplicate histories under different equipment IDs can cross folds.**

Upload validation checks duplicate equipment/cycle pairs (`backend/app/experiments/datasets.py:67`), and split assignment groups the equipment-ID strings (`backend/app/models/splits.py:23`). It does not ensure different IDs represent different histories.

The chair created 60 IDs containing the same 120-cycle trace. Upload validation and profile usability passed. Sidekick's existing history-identity helper found just **one distinct history**, present in both a training and validation fold and in both development and reserved assignments. No model was fitted, so this review does not claim a measured increase in accuracy. It establishes that the advertised independence can be violated and the apparent sample size overstated.

The later exposure ledger can block reserved identities already used in development; it does not repair contaminated development comparisons. Previously exposed checks also do not by themselves establish uniqueness inside a newly submitted reserved batch.

**Repair:** reject or group exact duplicate history identities before splitting, and require distinct identities in the reserved evaluation batch. Keep identity checks independent of user labels. Related records from the same real asset need an agreed grouping policy in a pilot; exact hashing cannot establish all statistical independence.

**F4 — P2/medium: accepted inputs can leave training folds with one label class.**

`backend/app/data/profiler.py:237` admits positive label coverage without verifying both label classes in every training fold. Logistic regression is subsequently fitted in `backend/app/models/candidates.py:45`.

A fixture with 26 varying-sensor histories, one long and 25 short, passed upload validation and custom fault coverage with onset 20 and seed 0. Six histories were assigned to development; every training fold's scorable labels contained only class `1`. The label condition was reproduced without fitting. The downstream classifier failure follows from its two-class requirement; no training job was launched.

**Repair:** check scorable samples and both classes for every training fold before consuming a run or marking development exposed. Include short histories, empty scorable folds and highly uneven lifetimes in tests. This is an explicit job failure risk, not silent fabrication of finished results.

**F5 — P2/medium: a valid long warning window crashes augmentation.**

`backend/app/models/train.py:76` samples onset with `integers(min_useful_lead + 5, 120)`. Schema ordering allows a minimum useful lead of 115 with horizon 130 and early boundary 145. The chair instantiated that protocol and called the sampler; it raised `ValueError: low >= high`.

This reproduces schema-to-sampler incompatibility, not a complete long-history job. Actual histories must also satisfy protocol coverage. **Repair:** derive a valid onset interval from the protocol and available histories, or reject unsupported settings before reservation. Cover the 114/115 boundary explicitly.

**F6 — P2/medium: gapped cycle indexes mix cycle and row semantics.**

`backend/app/data/profiler.py:78` warns about gaps but permits them. Feature windows operate on rows (`backend/app/features/build.py:86`), consecutive alert counts on adjacent readings (`backend/app/scoring/episodes.py:33`), and transient faults also use row spans. Timing labels continue to use operating cycles.

For readings at cycles 1, 11 and 21, adjacent observations are not adjacent cycles. A 20-reading window can span 190 cycles, and two high observations separated by ten cycles can satisfy a two-consecutive-reading rule. The existing warning is helpful, but cannot resolve the protocol interpretation.

**Repair:** for this prototype, reject non-unit cycle increments unless the full semantics are made gap-aware. Alternatively explicitly define and consistently label observation-based rules and coverage. Do not imply the gap warning is absent or secretly ignored.

### 3. Keep local deployment local and recover existing analysis work

**F7 — P1/high: Docker publishes unauthenticated full mode beyond loopback.**

`docker-compose.yml:11` publishes `8000:8000` with full mode enabled; the web port is similarly published. Full-mode access checks do not enforce visitor ownership (`backend/app/api/routes_experiments.py:44`). The POST origin check only rejects a supplied disallowed Origin, so a direct network client can omit that header.

If host networking/firewall permits access, another machine can reach local data and full-mode actions. This is configuration/source evidence, not an attempted network intrusion. It does not imply the separately guarded hosted demo or ordinary loopback PowerShell server has the same exposure.

**Repair:** publish the host ports as `127.0.0.1:8000:8000` and `127.0.0.1:5173:5173` for local development. Keep the container listening on its required container interface. Add authenticated access only if remote full-mode sharing becomes an explicit product requirement.

**F8 — P2/medium: one failed analysis status read stops polling.**

The effect at `frontend/src/components/AnalysisProvider.tsx:126` schedules one status read and depends on `record`. A failed read sets only an error; the record does not change, so no new poll is scheduled. The server can finish while the interface remains stuck.

The retry action at line 196 starts a fresh analysis with forced reuse disabled; `run` also cancels a prior active record. A temporary connectivity problem can therefore lead to unnecessary provider work rather than recovering the existing analysis. This was verified in source, not by browser network fault injection.

**Repair:** retry/back off reads for the same analysis ID, clear transient read errors on recovery, and distinguish refreshing status from intentionally rerunning with AI. Add a test where one GET fails and the next returns completion.

**F9 — P2/medium: public record creation has no aggregate storage bound.**

Analysis creation can persist a new record on each forced request (`backend/app/assistant/service.py:82`), and demo folders are created without an aggregate count bound (`backend/app/experiments/library.py:61`). Public analyses expire after 24 hours (`backend/app/assistant/store.py:131`), and there are useful payload, ownership and training limits, but expiry alone does not bound the volume created within that period.

This is a public-demo availability risk inferred from code; no load test or abuse simulation was performed. **Repair:** use bounded total storage/capacity, appropriate deduplication and folder/record safeguards. This need not reinstate the user-facing live-analysis allowance the owner explicitly removed.

### 4. Finish accessibility, identity and performance details

**F10 — P2/medium: overview canvas ignores reduced motion.**

`frontend/src/components/Layout.tsx:123` passes `respectReducedMotion={false}` even though the Cult canvas adaptation supports the preference. The review browser reported reduced motion enabled. The override is source-verified; no claim is made that every animation in Sidekick ignores the preference.

**Repair:** restore the component default/preference handling and show a static grid when reduced motion is requested. Keep manual replay navigation available. Review rolling numbers and the border beam under the same preference rather than assuming their behavior from the canvas alone.

**F11 — P3/low: result identity loses the library name.**

The library has a meaningful display label, but `frontend/src/components/Layout.tsx:50` reduces experiment context to “Uploaded-data experiment” or “Synthetic experiment”, with creation time and UUID in supporting disclosure. Multiple renamed experiments become hard to distinguish across result tabs.

**Repair:** carry the library display name, or original experiment name when absent, into visible result context alongside source and partition. Preserve immutable recorded names and identifiers.

**F12 — P3/low: “Modified” displays creation time.**

`frontend/src/components/ExperimentLibrary.tsx:377` labels the date column “Modified”; `LibraryFileRow.tsx:68` renders `created_at`. Renaming or moving does not update that date.

**Repair:** label it “Created” or “Added”. Only introduce a separate organization-modified timestamp if that is genuinely useful; do not alter recorded experiment dates or date grouping as a side effect.

**F13 — P3/low: AI cache identity does not track the actual model/prompt.**

`backend/app/assistant/service.py:56` fingerprints the base analysis prompt and evidence digest. The configured model is absent, and the base analysis version differs from the investigation version used in the actual result. A model/prompt change can reuse an older analysis. The old record identifies its provenance and an explicit rerun exists, so this is a cache policy issue rather than stale recorded metrics.

**Repair:** decide and document versioned analysis reuse; if new model/prompt settings should take effect immediately, include those versions in the result cache identity while retaining edited brief continuity separately.

**F14 — P3/low: initial frontend payload is large.**

The production build reports a main JavaScript chunk of **776.92 kB minified / 241.95 kB gzip**, above Vite's warning threshold. Some page chunks are already lazy-loaded. Shared analysis, overview effects and font imports deserve bundle attribution before changing them.

**Repair:** measure startup on a modest device, then defer nonessential effects/analysis code and unused font subsets where worthwhile. No startup latency or frame-rate regression was measured, so do not present bundle size as proof the app is slow.

## Product and AI usefulness

An engineer would use Sidekick to answer: which candidate met the agreed warning rules, which sensor fault weakened it most, what happened in the stored history, and what evidence supports the next review decision. That is a coherent use case. It is currently a retrospective testing/review tool, not a live maintenance system.

The chair opened the local, deterministic analysis for `aug3`. It clearly showed 64/64 required cases passed, 98.75% weakest-fault detection against a 70% requirement, the highest early burden, a one-warning loss against healthy readings, and a channel-scaling/gradual-offset check. This is useful interpretation. The assessment repeats some headline facts and limitations, but those statements connect the facts to their meaning rather than merely listing the same table again. Keep the verdict first and supporting detail optional.

The paid AI's incremental value is not established by this review. Its strongest plausible contribution is selecting relevant cases and next checks from the verified evidence; its safe output boundaries also mean it is not a general engineering reasoning oracle. Existing automated evaluation checks references, claims and brevity (`scripts/evaluate_assistant.py`), but those checks do not establish that an engineer makes a better decision or saves meaningful review time.

The next product milestone should be one reviewing engineer, one equipment family, one agreed review decision and an existing procedure to compare against. Agree warning windows, realistic fault scenarios, independent histories and ground-truth quality before scoring. Measure review time, misunderstood results, useful follow-up checks and decisions supported. Compare deterministic analysis against AI-assisted analysis on the same evidence before paying for a larger model by default. Any live provider evaluation requires a separate authorized run; none happened here.

`PILOT.md` already acknowledges missing real-family/reviewer commitments. Complete failed histories cannot establish healthy-fleet false-warning rates, and cycle-based benchmark results cannot establish elapsed-time benefit. These are pilot limitations, not reasons to add unsupported censored/time-based processing in this review.

## Suggested repair order

1. Repair generated types and pilot fixtures; establish a reproducible green local/CI gate.
2. Add duplicate-identity and per-fold feasibility checks before reservation; fix augmentation bounds and settle gap semantics.
3. Bind Docker ports to loopback, then recover analysis status without rerunning existing work.
4. Add fixture-only library browser coverage; fix reduced motion and the two naming/date details.
5. Measure startup and AI incremental usefulness. Keep the existing visual system and avoid a broad redesign.

## Council resolution and limitations

All three members completed independent candidates and an anonymized peer round. Their strongest agreement was to preserve the evidence workflow and prioritize input validity/reliability. The chair retained the Docker and frontend recovery findings after reopening their cited code. Peer dissent lowered the one-class case to a job-failure issue, the cache case to a policy improvement, and bundle size to a measurement task. Votes were not used as proof.

All high findings were checked against current code. Medium/low findings were reviewed in source, but most were not exercised end-to-end; each entry identifies when a direct probe or browser check occurred. The review did not perform a network penetration test, volumetric test, field study, full assistive-technology audit, paid AI evaluation or model training.

<details>
<summary>Claims deliberately not adopted</summary>

- Pilot setup errors do not prove the real pilot feature is broken; the concrete failure is an invalid fixture and red gate.
- No reserved-data fitting leak was established. Full-data profiling/fault eligibility is not automatically equivalent to fitting on reserved predictions; any claim of complete statistical blinding requires an agreed study protocol.
- Generic deployment warnings are appropriate to the recorded evidence. Their presence is not proof of a broken analysis feature.
- Duplicate screen-reader text in the streaming DOM is not a demonstrated duplicate visual paragraph; the inspected screenshot showed one visible copy.
- The mobile library and protocol view did not require a replacement design. Natural vertical scrolling for details is appropriate.
- A larger language model, more animation, live monitoring, nested folders or an unconstrained chat feature is not justified by this review.

</details>

## Reproduction evidence

The chair's isolated, no-fit probes produced:

```json
{
  "duplicate_histories": {
    "accepted_by_upload_validation": true,
    "profile_usable": true,
    "equipment_ids": 60,
    "distinct_history_identities": 1,
    "train_validation_identity_overlap": 1,
    "development_reserved_identity_overlap": 1
  },
  "single_class_folds": {
    "accepted_by_upload_validation": true,
    "profile_usable": true,
    "protocol_coverage_passed": true,
    "seed": 0,
    "development_histories": 6,
    "training_fold_classes": [[1], [1], [1], [1], [1]]
  },
  "long_protocol": {
    "accepted": true,
    "augmentation_error": "low >= high"
  }
}
```

Supporting scripts, fixture CSVs, candidate drafts and expected generated types were written only under ignored `output/council-review-2026-10-09/`. This report includes their consequential results so it remains understandable without those temporary files. Application implementation was left unchanged.
