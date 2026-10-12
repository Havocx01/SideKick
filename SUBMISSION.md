# Sidekick V2 reviewer handoff

**Sidekick: Stress-testing predictive maintenance warnings**

Sidekick checks whether equipment failure-warning models still warn in time when
sensor readings go missing, freeze or drift. Engineers review the data and protocol,
compare models, inspect the weakest simulated fault cases and export the evidence.
Local workflows include CSV uploads, synthetic training, model freezing and a
separate one-time reserved-equipment evaluation.

Recorded NASA C-MAPSS simulated-engine evidence and synthetic samples demonstrate
the workflow. They do not establish ABB field performance, deployment approval or
maintenance savings. Optional deep AI proposes tentative explanations and diagnostic
questions; recorded metrics and verdicts remain server-owned. Its consistent extra
benefit over regular analysis has not been measured.

## Open the app

Prepare dependencies and build on the presentation laptop before travelling. From
the repository root, run `.\tasks.ps1 api`, then open <http://127.0.0.1:8140>.
Keep the terminal open. Alternatively, double-click **Start Sidekick.cmd**; first
installation needs internet. Later recorded-evidence workflows need no API key.

**View walkthrough** opens the introductory disclosure. **Explore benchmark** opens
model comparison. **Set up sample** and **Upload CSV** prepare new local experiments.

## Judge-facing demo

Use the [five-minute or two-minute runbook](docs/judging-guide.md), with lr2's recorded
sensor-dropout failure and aug3's separately recorded result. Precompute training
before presenting; show an existing synthetic run if asked. Do not repeat reserved
scoring during the presentation.

Current offline media/reports are prepared under `output/judging-20261012/` on the
presentation machine. Copy the verified package to another laptop or USB drive.
The v1.5 images/video in `media/submission/` are historical. Use the fresh V2 recording.
See [judging readiness](docs/arc/audits/2026-10-12-judging-readiness.md) for actual
verification results and remaining prerequisites.

Repository: <https://github.com/Havocx01/SideKick>. The README's public demo is a
separate restricted environment. Do not assume it contains this local revision or
rely on it for judging without a separate smoke check.
