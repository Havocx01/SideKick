# Nebius x NVIDIA submission details

Track: **Best Apps and Agents**. Project: **Sidekick**.

## What it does

Sidekick helps reliability and data engineers investigate equipment-warning models under unreliable sensor readings. An engineer fixes a model context, concern, criterion, fault profile and allowances. NVIDIA Nemotron proposes bounded experiments; deterministic code measures matched clean/faulted outcomes. Findings can be replayed, reduced, exported as regressions and compared with explicit remedies.

The supported decision is which model, warning rule and sensor-failure cases to take to further supervised testing. Real-equipment benefits and maintenance savings have not been established.

## Technology and services

- **NVIDIA model:** `nvidia/nemotron-3-super-120b-a12b`, served through Nebius Token Factory's compatible Chat Completions API.
- **Nebius contribution:** hosted inference for structured experiment proposals without operating a separate model-serving stack. Token Factory is the Nebius service used; no Serverless Jobs, Serverless Endpoints or AI Cloud deployment is claimed.
- **Tavily:** an explicit fault-research search retrieves references for a separate Nemotron summary. Query preview, consent, bounded excerpts, citation checks and saved results control the action.
- **Application:** React, TypeScript and Vite; Python, FastAPI and Pydantic; SQLite; NumPy, pandas, SciPy, scikit-learn and XGBoost.
- **Execution:** durable limits, duplicate handling, cancellation, leases, background operations and checksummed finite worker jobs. Linux context/worker deployment uses Python 3.11.9 and pinned numerical dependencies.

The model's hypotheses and external references never determine a measured finding or change the policy automatically. Raw histories and fitted objects remain local unless their separate worker transfer is authorized.

## Significant updates to the earlier project

The earlier ABB Accelerator Sidekick V2 compared equipment-warning models under fixed single-sensor tests. The adaptation adds:

- Nebius/Nemotron provider integration and reasoning allowances.
- Typed compound faults, versioned profiles and fixed development evaluation.
- Persistent investigations, bounded execution and adaptive proposal/result feedback.
- Fault-specific provider schemas, timing coverage and corrective feedback.
- Deterministic finding criteria, hypothesis lineage, reduction and regression export.
- Remedy comparisons with costs, clean performance and unresolved failures.
- Search benchmarks, HTTP/background execution and the browser workbench.
- Frozen-procedure assessment on fresh histories with exposure tracking.
- Containerized remote workers, public evidence and recorded hosted investigations.
- Optional Tavily research with cached citations and separate evidence limits.

The Git history preserves the earlier project and the individual implementation commits. Feature implementation dates and saved capture dates are evidence of when work occurred; later changes must not be attributed to an earlier submission period.

## Recorded results

Every number below comes from a file in `evidence/`, captured on Windows (Python 3.11.9 with the versions pinned in `docker/runtime-constraints.txt`), replayed and exported without private data. Results are tied to their saved fitted contexts and recorded code revisions; they are historical evidence, not guarantees for a newly prepared model. All data is synthetic; real equipment performance and maintenance savings are not established. Prediction bytes can differ between platforms, so replay digests are checked per platform.

### Live experiment selection

The [default-context run](../evidence/investigations/nemotron-live-default.json) allowed 4 calls and 16,384 completion tokens. Nemotron made 3 calls, all accepted, reporting 1,121 tokens; each later proposal cited earlier results and tried a new fault family, and each was evaluated on 22 of 22 histories. None met the failure criterion. The [recorded comparison](../evidence/benchmarks/nemotron-default-context.json) on that context, with the same criterion and 4-experiment allowance, found no failure for Nemotron or for the fixed suite, random search and hill climber (5 seeds each). Nemotron cost 3 provider calls and about 15 seconds against about 0.1 seconds for each baseline. It does not establish search superiority. On the [synthetic fixture](../evidence/benchmarks/synthetic-fixture.json) at demonstration thresholds, random search found 5 failure families in 6 of 10 runs, the hill climber 2 in 1 of 10 and the fixed suite none; that comparison is not interchangeable with the live one.

### A failure Nemotron chose

The [browser-run investigation](../evidence/investigations/nemotron-live-browser.json) was started from the workbench with a 2-call, 8,192-token allowance at the deliberately fragile 0.95 demonstration threshold. Nemotron's one call cited the four earlier results and proposed stuck ambient temperature with a negative bearing-temperature drift. Useful warnings fell from 22/22 to 21/22, a measured failure under the saved criterion. It replayed exactly and reduced to both faults from 20 cycles before failure with a −2.0 SD drift, component-minimal and minimal on the tested grid ([regression](../evidence/regressions/nemotron-live-browser.json)). A 0.5 threshold resolved it. Frozen and assessed once on 12 fresh synthetic histories, it did not reproduce: a one-warning development effect was not robust.

### Supplied failure, reduction, remedy and fresh assessment

The [full demonstration](../evidence/investigations/nemotron-live-demo.json) uses the same 0.95 threshold. A supplied stuck vibration and oil-particle case, not chosen by Nemotron, reduced useful warnings from 22/22 to 18/22. It replayed exactly and reduced to oil particles stuck from 30 and vibration stuck from 60 cycles before failure ([regression](../evidence/regressions/nemotron-live-demo.json)); claims are limited to tested removals and the specified grid. A 0.5 threshold resolved both development cases, degraded none and kept clean detection at 100% while median lead rose from 17 to 19 cycles. Assessed once on 12 fresh synthetic histories, both cases still failed with and without the remedy, so the development improvement did not generalize. Nemotron's two accepted proposals in this run, after one rejected citation, were not failures.

The [default-threshold export](../evidence/investigations/synthetic-recorded.json) contains six supplied cases and no measured failure. Historical NASA FD001 evidence remains exposed and is not a fresh holdout.

### Earlier live checks

Sanitized captures from the first live runs are kept privately. With prompt v3 every reply was rejected: explicit onsets combined with seeds, inapplicable parameters and cross-group pairs. With v4 one reply reached the evaluator but its onset was beyond every development history. Prompt v5 added fault-specific schema alternatives, dataset-aware timing and corrective feedback; every live run since produced scorable experiments.

### Tavily runtime verification

The initial research action made one successful Tavily request, reporting one credit, and one Nemotron request, reporting 265 completion tokens. The search returned unrelated Microsoft pages; Nemotron declined sensor-specific advice. The final technical-term filter rejects those captured sources offline.

A second live check with the final code, on the demonstration's measured stuck-sensor failure, used one Tavily credit and one Nemotron request (369 reported completion tokens). Two general predictive-maintenance pages passed the filter. Nemotron stated that they do not describe diagnostics for stuck signals and suggested three supervised checks: high-rate logging of the affected channels, cross-channel comparison and an injected test signal. Each test cited a source, but the sources support only the general premise, not the specific procedures; the third citation in particular is loose. The workbench therefore labels research as unverified context that never changes a measured finding.

## Service feedback

Token Factory's compatible API fitted the existing Python application. Usage metadata, including reasoning tokens, supported exact saved accounting. Strict JSON-schema output worked with `$defs`, `$ref`, `anyOf`, `enum` and numeric bounds; we expressed each fault variant with `anyOf` and `enum` rather than `const`, `oneOf` or discriminators. Replies were always well-formed JSON; remaining failures were semantic, such as citing a result that did not exist or annotating a citation with prose, and short local feedback let the next call correct them within the same allowance. With low reasoning effort, recorded calls took about 3 to 6 seconds and reported 290 to 710 completion tokens. Initial domain-invalid replies motivated explicit schema alternatives and timing-coverage feedback; strict JSON alone did not enforce the whole experiment contract. Clear examples of nested alternatives and reasoning-token accounting would help similar integrations.

These latency and token observations come from a handful of calls and are not service-wide performance claims. Tavily's first response was irrelevant to the supplied query; source screening and the model's abstention prevented unsupported sensor advice from being treated as evidence.

## Submission artifacts

- [Public repository](https://github.com/Havocx01/SideKick), with the root MIT license.
- [Public demo](https://sidekick-e9lu.onrender.com/); verify its reported deployed revision.
- [Setup and reproduction](../README.md) and [reviewer guide](../SUBMISSION.md).
- An engineer review is still needed before usefulness can be claimed; see `docs/sidekick-engineer-evaluation.md`.
- The owner must supply the public YouTube video link and final Devpost entry. The video should remain under three minutes and identify recorded versus live footage, synthetic data and supplied versus model-selected cases.
