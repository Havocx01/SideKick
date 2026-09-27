# Submission handoff

## Suggested title

Sidekick: Stress-testing predictive maintenance models

## Description

Sidekick checks whether equipment failure-warning models remain useful when
sensor readings go missing, freeze or drift. Engineers choose detection and
early-alarm limits, train candidate models, inspect their performance under
simulated faults and export the supporting evidence.

The prototype includes a recorded NASA C-MAPSS benchmark, a compact hosted sample
that performs real training, and a local workflow for CSV uploads and larger
experiments. The Evidence guide explains the selected run using its recorded
metrics. No API key is required.

Sidekick can report that no model qualifies. It does not certify models, approve
deployment or establish field performance on ABB equipment. Its evidence exports
include configuration, data fingerprints, source identifiers and limitations.

## Form entries

- Parent submission: select the existing Sidekick idea-phase entry.
- Theme: select Theme 1 used for the parent submission.
- Repository: https://github.com/Havocx01/SideKick
- Demo link: use the existing Render service URL after the live checks below pass.
- Video: review `media/demo.mp4` before uploading. It predates the compact hosted
  workflow; do not describe recorded benchmark footage as a newly executed run.
- Presentation: upload the final deck after checking it describes the same scope.
- Source code: use the fresh ZIP in `artifacts/submission/`, not an older export.
- Snapshots: use the three PNG files in `media/submission/`.

## Instructions to run

Open the hosted demo and choose **Run sample experiment**, then **Generate sample
data**. Review the split and keep the demonstration settings of 70% detection
and 10% early-alarm burden. Select **Train and challenge models**. The server
performs real training and opens the comparison when finished.

Read the decision summary, try an Evidence guide question, open **Warning replay**
and download **Export evidence**. For a second run, try 100% detection and 0%
early-alarm burden. The current compact sample produces a valid no-model-qualifies
outcome under those stricter criteria.

If the shared server is busy or at its allowance, explore the recorded NASA
benchmark. CSV uploads and the larger sample are available locally using the
README commands. No API key is needed.

## Short demo walkthrough

1. Explain the question: will failure warnings survive faulty sensors?
2. Show that the NASA benchmark is recorded and the sample starts a new run.
3. Generate the hosted sample, explain the ten evaluated and twenty unscored histories.
4. Start training and show its actual stages.
5. Explain detection, early alarms and the chosen model. Do not assume augmented
   training helped; read the measured comparison.
6. Replay a machine's warnings and export the evidence.
7. Close with the limitation: simulated experiments support evaluation, not deployment approval.

## Deployment checks before submitting

The repository keeps Render's free plan. The default Docker target includes
training dependencies and uses `SIDEKICK_MODE=demo`. If the service was created
manually, change its existing environment setting from `replay` to `demo` after
building this revision. A Blueprint deployment should use the updated render.yaml.
Serve frontend and API from the same origin, with one Uvicorn worker.

Render supplies the public origin automatically. Other reverse proxies should
set `SIDEKICK_PUBLIC_ORIGIN` to the public HTTPS origin. The demo uses a secure,
HttpOnly cookie for access to temporary results. No account or API key is needed.

After deployment:

1. Check `/api/health`: mode `demo`, `can_train: true`, `can_upload: false`.
2. Complete the hosted sample on the live URL, then refresh and export its evidence.
3. In a private browser window, confirm the first browser's experiment URL is unavailable.
4. Check the recorded benchmark and download its evidence separately.
5. Confirm the three screenshots, demo video and proposal describe the current behavior.

Render's free service may sleep after inactivity and loses temporary files on
restarts, redeploys and idle shutdowns. Export results promptly. See
[Render's free service limitations](https://render.com/docs/free).

## Verification scope

Local checks cover browser isolation, upload and mapping restrictions, quotas,
request size limits, HTTPS proxy handling, expiry cleanup, cancellation, timeout,
restart recovery and compatibility with full and replay modes. A real compact
sample and a stricter no-qualification run both completed locally; exported
metrics matched the selected experiments and reserved histories remained unscored.

The initial compact-sample measurement was about 432 MiB combined resident memory
on Windows, compared with about 503 MiB for the larger sample. These measurements
are not a guarantee of Linux memory use or hosted latency. Docker's Linux engine
was unavailable during verification, so the container and live service still
need the checks above before claiming the deployment is verified.
