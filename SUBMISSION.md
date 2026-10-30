# Sidekick reviewer guide

Sidekick is an AI-assisted investigation workbench for engineers testing whether equipment-warning models tolerate unreliable sensors. The submission track is **Best Apps and Agents**.

## Inspect the public demo

Open [Sidekick](https://sidekick-e9lu.onrender.com/) and choose **Investigations**. Recorded runs are available without keys or installation and are labelled **Recorded, not live**. The page shows who selected each scenario, coverage, measured outcomes, reductions and remedy limits. It does not initiate provider calls.

The deployed revision is reported by `/api/health`. Compare it with the submitted commit; an older deployment does not establish that the latest code is hosted.

## Run the complete local example

Follow the [README setup](README.md#start-here), then run:

```powershell
.venv\Scripts\python.exe scripts/demo_investigation.py
```

Open **Investigations** and select **Demo: find sensor faults...**. This no-key example uses supplied synthetic cases and a deliberately fragile 0.95 threshold. It reproduces a compound failure, reduces it, exports a regression, compares a 0.5 threshold remedy and assesses a frozen procedure on fresh synthetic histories. Exact counts belong to the newly fitted context.

For real Nemotron proposals, configure the server-side Nebius key and explicit workspace/action permission as described in the [README](README.md#nvidia-nebius-and-tavily). Optional Tavily fault research also needs its own key and per-action consent. Neither feature starts automatically.

## Evidence to inspect

- [Nemotron on the default context](evidence/investigations/nemotron-live-default.json): three accepted proposals with full 22-history coverage; no qualifying failure. Its [recorded comparison](evidence/benchmarks/nemotron-default-context.json) found no failure for any strategy.
- [A failure Nemotron chose](evidence/investigations/nemotron-live-browser.json): started from the browser; one lost warning that replayed and reduced but did not reproduce on fresh histories.
- [Supplied compound demonstration](evidence/investigations/nemotron-live-demo.json): 22/22 to 18/22 useful warnings at the demonstration threshold; replayed, reduced, remedied in development, still failing on fresh histories.
- [Default-threshold example](evidence/investigations/synthetic-recorded.json): six supplied cases with no measured failure.

These aggregate exports contain no raw histories, equipment identifiers, private objectives, fitted objects or credentials. Their digests establish integrity, not authenticity. They were made from the final code; a fresh checkout reproduces their measurements, while replay digests are checked per platform.

## Three-minute demonstration

Show the local workbench, recorded real Nemotron proposals and call accounting, the supplied failure and its coverage, recorded replay/reduction, the remedy and unresolved stronger failure, then the public export. Clearly label the synthetic data, fragile threshold and recorded footage. Do not present a supplied case as an AI discovery.

The project description, earlier-versus-new work and service feedback are in [submission details](docs/nebius-submission.md). Test commands and runtime limits are in [TESTING.md](TESTING.md). The public repository is [Havocx01/SideKick](https://github.com/Havocx01/SideKick), licensed under MIT.
