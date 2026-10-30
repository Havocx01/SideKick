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

All results below are synthetic and specific to their saved fitted contexts.

### Live experiment selection

The [recorded live investigation](../evidence/investigations/nemotron-live-recorded.json) used three accepted Nemotron proposals, each evaluated on all 22 development histories. Later proposals referenced earlier measured results. The run reported 1,083 completion tokens, and recorded request times were approximately 2.8–4.1 seconds. None of its scenarios met the failure criterion.

The recorded comparison on that context found no qualifying failure for Nemotron or the fixed, random and hill-climbing comparators under the compared allowance. It does not establish search superiority. An earlier, separate benchmark using different demonstration thresholds found failures with constrained random search; that is not interchangeable with the live comparison.

### Supplied failure, reduction and remedy

The [compound demonstration](../evidence/investigations/compound-demo-recorded.json) deliberately uses a fragile 0.95 threshold. A supplied stuck vibration/oil-particle case reduced useful warnings from 22/22 to 8/22: six became missed and eight became late. It was not discovered by Nemotron.

The case replayed exactly and reduced to later onsets while retaining both components. Claims are limited to tested single-component removals and the specified grid, not a global minimum. A 0.5 threshold remedy resolved the reduced case and degraded none of the previously passing tested cases, but the stronger original case remained a failure.

### Fresh synthetic assessment

The [frozen-procedure assessment](../evidence/investigations/fresh-validation-recorded.json) used 12 fresh synthetic histories. For the reduced case, the remedy changed useful warnings from 8/12 to 12/12. For the stronger original case it changed 0/12 to 5/12, still a failure. This establishes neither field performance nor general remedy effectiveness.

The [default-threshold export](../evidence/investigations/synthetic-recorded.json) contains six supplied cases and no measured failure. Historical NASA FD001 evidence remains exposed and is not a fresh holdout.

### Tavily runtime verification

The initial research action made one successful Tavily request, reporting one credit, and one Nemotron request, reporting 265 completion tokens. The search returned unrelated Microsoft pages; Nemotron declined sensor-specific advice. The final technical-term filter rejects those captured sources offline. Useful live retrieval remains unverified, and no further paid call was made under that allowance.

## Service feedback

Token Factory's compatible API fitted the existing Python application. Usage metadata supported saved accounting. Initial domain-invalid replies motivated explicit schema alternatives and timing-coverage feedback; strict JSON alone did not enforce the whole experiment contract. Clear examples of nested alternatives and reasoning-token accounting would help similar integrations.

The small recorded latency and token observations above are not service-wide performance claims. Tavily's first response was irrelevant to the supplied query; source screening and the model's abstention prevented unsupported sensor advice from being treated as evidence.

## Submission artifacts

- [Public repository](https://github.com/Havocx01/SideKick), with the root MIT license.
- [Public demo](https://sidekick-e9lu.onrender.com/); verify its reported deployed revision.
- [Setup and reproduction](../README.md) and [reviewer guide](../SUBMISSION.md).
- The owner must supply the public YouTube video link and final Devpost entry. The video should remain under three minutes and identify recorded versus live footage, synthetic data and supplied versus model-selected cases.
