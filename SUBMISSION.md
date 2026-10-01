# Submission handoff

## Sidekick: Stress-testing predictive maintenance models

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
- Demo link: https://sidekick-e9lu.onrender.com/
- Video: review `media/demo.mp4` before uploading. It predates the compact hosted
  workflow; do not describe recorded benchmark footage as a newly executed run.
- Presentation: upload the final deck after checking it describes the same scope.
- Source code: use the fresh ZIP in `artifacts/submission/`, not an older export.
- Snapshots: use `01-start.jpg`, `02-comparison.jpg` and `03-replay.jpg` in `media/submission/`.

The document in `idea phase/documents/` describes the original plan, not the
finished prototype. The final deck must describe the recorded Evidence guide,
fixed warning windows, and evidence ZIP exports. An external LLM copilot,
exported prediction endpoint, and adjustable prediction horizon are not shipped.

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

## Live presentation walkthrough

Use the local built app as the main live demo. Keep the public URL available for judges, but open it before the session because the free service may need to wake up. Use genuine captures from `media/submission/` in the deck. The older illustrative images and video do not show this finished workflow.

Start the app before presenting. After installation and a frontend build, run:

```powershell
$env:SIDEKICK_MODE = 'full'
.\tasks.ps1 api
```

Open http://127.0.0.1:8000. Keep that terminal open. The built app needs no separate frontend server, internet connection or API key to explore the benchmark and run synthetic experiments.

Rehearse this sequence:

1. **Start:** explain the question: will failure warnings survive a faulty sensor? Choose **Explore benchmark** and identify it as recorded evidence.
2. **Fragile candidate:** select logistic regression `lr2`. It has 80/80 clean useful detections but only 41/80 in its weakest required case, sensor 8 dropout. Scroll to the required heatmap and outcome breakdown: 24 warnings were late, 15 were missed. [Open that view](http://127.0.0.1:8000/comparison?candidate=logistic_regression%2Flr2#fault-results).
3. **Qualifying candidates:** return to the leading candidates. XGBoost `xgb1` and augmented `aug3` both retain 79/80 useful detections in their weakest required case. Do not present this as proof that augmentation caused a large improvement.
4. **Warning replay:** [open engine 13](http://127.0.0.1:8000/replay?equipment=13&scenario=drift-persistent-sensor_3-on60-sd1-neg). For the recommended recorded model, warning lead time changes from 26 to 24 cycles with drift injected. Show the fault-onset marker and the altered sensor trace. This is not a replay of the failing logistic-regression model.
5. **Evidence:** ask one Evidence guide question, follow its source link, and download **Export evidence**. Show the HTML report, metrics CSV and provenance.
6. **Real execution:** if timing permits, run a new synthetic experiment through the browser. Explain the 40 development histories, five folds and 20 unscored reserved histories. Use the completed local synthetic experiment if the live run is still working; label it as an earlier run. The full sample completed in about 47 seconds on the test laptop; this is a measurement, not a promised runtime.
7. **Close:** these simulated tests support further evaluation. They do not certify models or establish performance on ABB assets.

On the presentation laptop, a completed local sample and a stricter no-model-qualified run are saved in **Your experiments**. A fresh installation starts with an empty experiment workspace. For the stricter run, use 100% useful detection and 0% early-alarm burden. Check this state during rehearsal, but keep it out of the main walkthrough unless time permits or a judge asks.

## Demo results to use accurately

- 256 unique injected fault scenarios in the recorded benchmark; 64 are required for qualification.
- 2,570 result records across ten configurations, including clean cases. This is not 2,570 independent faults or additional equipment histories.
- Ordinary and augmented leading XGBoost configurations both have 98.75% worst required detection. The augmented configuration's mean advantage is 0.04 percentage points, with 0.04 percentage points higher clean alarm burden.
- The 70% detection and 10% burden defaults demonstrate configurable acceptance criteria. They are not plant-safety standards.
- Warning time is in operating cycles. Useful detection requires an alert to be active in the 10-to-30-cycle window; an episode can have opened earlier.

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
are not a guarantee of Linux memory use or hosted latency.

On 27 September 2026, the public Render demo completed a real sample run in
27.8 seconds. Its comparison, Evidence guide, export and page refresh worked.
A separate browser received 404 for that experiment and its export. All 52 CSV
metric rows matched the JSON evidence; the reserved histories remained unscored.
The tested deployment reported commit `68fa6fe0240c5852d9be0fd838a6385172336303`.
This verifies one hosted run, not a load test or an uptime guarantee.

A clean local environment installed the declared training dependencies and ran
the sample without OpenAI, multipart, SHAP, matplotlib or an API key. Eleven job
and access regression tests passed, along with upload validation, fingerprint,
partition and export checks. Desktop and mobile layouts were checked in both
themes. Docker's local Linux engine remained unavailable; the deployed Render
service supplied the hosted verification above.

The local presentation revision shortens the result summary, labels required and supplemental fault cases separately, displays numeric heatmap values, supports shareable candidate and replay selections, and compares clean/faulted warnings directly. Readable labels also appear in the Evidence guide and HTML export. No model families, acceptance rules, API schemas or training resource limits changed.

Before judges use the public link, deploy this revision and repeat its short health, comparison, replay and export checks. The presentation and any video must use the finished interface and claims above.


On 30 September 2026, the full local sample completed in 46.6 seconds and the stricter run completed in 26.5 seconds with no qualifying model. Each produced 370 scenario records, kept all 20 reserved histories unscored, and stored its own acceptance-criteria fingerprint. CSV metrics matched JSON evidence. All 11 archived job/access regression tests and 11 upload/mapping scenarios passed. Candidate and replay links, invalid selections, Evidence guide anchors, experiment switching and refresh persistence were checked in the browser. The desktop leaderboard fits at 1366 by 768, mobile layouts were checked at 390 by 844, both themes were inspected, and the Impeccable detector reported no findings. These are local checks of this revision; the public service still needs a deployment and a short smoke check.
