# Sidekick judging guide

The organizer has not supplied a presentation duration or judging rubric. These
timings are adjustable rehearsal targets, not the confirmed event schedule.

## Main message

**A model can look successful on healthy sensors and lose failure warnings when a
sensor stops working. Sidekick makes that weakness visible before a field pilot.**

Sidekick is an evidence-review and validation workbench. It is not a live industrial
monitor, a physical-failure diagnosis or an approval to deploy a model.

## Five-minute presentation

| Time | Show | Say |
|---|---|---|
| 0:00–0:35 | Overview | “Predictive maintenance depends on sensors. We test what happens to the warning when a sensor goes missing, freezes or drifts.” |
| 0:35–1:10 | Data and protocol, Overview | “These are recorded NASA C-MAPSS simulated-engine histories. The protocol defines when a warning counts, and separates model selection from reserved validation.” |
| 1:10–2:05 | Model comparison, Logistic regression · lr2 | “On healthy readings, this model warns in time for 80 of 80 development histories. Under its weakest required dropout case, that falls to 41 of 80. A clean-data result alone misses that weakness.” |
| 2:05–2:55 | lr2 weakest-case replay | “This is a stored example, not a new inference run or a fleet-wide claim. Compare the clean and faulted warnings against the same useful window.” |
| 2:55–3:40 | Compare lr2 with Augmented XGBoost · aug3 | “aug3 meets all 64 required recorded fault cases; lr2 meets 57. This supports selecting a candidate for further validation. The worst faults differ, so it does not prove augmentation caused the difference.” |
| 3:40–4:20 | Analyze result and saved review brief/report | “The next check is tied to the recorded case, with linked evidence. We can edit the review draft and export it without changing the original results.” |
| 4:20–5:00 | Next-step slide | “The next milestone is one equipment family, an engineer-agreed protocol and fresh representative histories. We need to measure whether this improves actual review decisions.” |

If AI is central to your pitch, substitute up to 30 seconds with an already verified
**saved** deep investigation. AI suggests checks and tentative explanations; it does
not create the measurements or verdict. A report with no retained explanation is
a question-only result, not a diagnosis. Do not buy an untested answer during the talk.

## Two-minute version

1. **20 seconds:** Explain sensor faults as a blind spot in clean-data evaluation.
2. **40 seconds:** Show lr2 changing from 80/80 timely warnings to 41/80 in its weakest
   simulated dropout case; identify recorded benchmark and development scope.
3. **35 seconds:** Show the corresponding stored replay and candidate comparison.
4. **25 seconds:** Show the export and close with the proposed real-equipment pilot.

## Six-slide outline

1. **Problem:** A reliable-looking warning model can fail when its sensors do.
2. **Workflow:** Data/protocol → train and challenge → inspect → preserve evidence
   → separately validate a frozen candidate.
3. **Demonstration:** lr2 healthy 80/80 versus weakest dropout 41/80; one stored trace.
4. **Results:** aug3 passes 64/64 required cases; lr2 passes 57/64. Different worst
   faults and selected configurations limit causal comparisons.
5. **Engineer value:** Find failure-sensitive cases, agree a follow-up check and share
   reproducible evidence. Review time and maintenance savings remain unmeasured.
6. **Next step:** One equipment family, reviewing engineer, suitable complete history
   data and an agreed protocol/decision. No invented ROI or production claim.

Keep implementation details for Q&A. Split speaking sections between team members;
give one person control of the demo laptop.

## Laptop setup and rehearsal

Install/build before leaving while internet is available. Rehearse on the presentation
laptop with its actual display scaling, charger and HDMI/USB-C adapter. Disable
notifications, close unrelated tabs and keep Sidekick's terminal open.

Open Overview, then **Data and protocol**, then
<http://127.0.0.1:8140/comparison?candidate=logistic_regression%2Flr2>. Follow
**Replay weakest detection case** from fault details so model/scenario/history stay
aligned. Keep an existing synthetic experiment available under **Experiments** if asked.

Preload results. Do not launch training, reserved scoring or paid AI during the timed
talk. Refresh once, reopen an analysis and verify a saved brief exports. Repeat with
Wi-Fi off; routine recorded-evidence workflows must work.

## Fallback ladder

1. If AI fails, explain that its interpretation was rejected and continue with regular
   recorded-evidence analysis. Do not present fallback as AI.
2. If the app/display fails, open `sidekick-v2-recorded-demo.webm` and the offline report
   under `output/judging-20261012/`. The video shows recorded benchmark evidence,
   not newly executed training or AI.
3. If video fails, use the numbered screenshots and local HTML report.
4. Carry a second package copy on another laptop/USB drive. A source ZIP alone lacks
   installed dependencies and is not a working offline installation.

Keep your full workspace backup private: it can contain uploads and personal drafts.
Only share the prepared report/ZIP/screenshots/video with judges.

## Likely questions

| Question | Accurate answer |
|---|---|
| Is this ABB field data? | No. The demo uses recorded NASA simulated-engine evidence and synthetic workflow tests. |
| Does a pass mean ready for production? | No. It means the candidate meets this recorded protocol's limits. Field validation and deployment remain separate. |
| Why use AI? | Optional diagnostic questions and tentative explanations. Routine analysis works locally; consistent extra benefit is not yet measured. |
| Can it ingest any telemetry? | No. It currently needs numeric sensors, integer consecutive cycles and complete failure histories. Timestamps, censored histories and healthy-only logs require another protocol. |
| Did augmentation cause improvement? | The selected-model comparison cannot establish that; inspect matched configurations and avoid causal claims from different worst cases. |
| What is the commercial benefit? | Better-directed validation/review is the intended benefit. Maintenance savings and reduced review time need a pilot. |
| What do you need from ABB? | One equipment family, a reviewing engineer, suitable history data and an agreed review decision/protocol. |

## What the team must confirm

The supplied organizer email requires individual registration, travel confirmation,
your laptops/materials and Wednesday awards attendance. Its **7 October** travel
confirmation deadline has passed. Confirm acceptance directly if not acknowledged.

The [official event home](https://events.abb.com/usaccelerators) lists **12–15 October
2026**. The public agenda does not expose your finalist talk duration. The email says
Tuesday 09:00 “CST”; public October sessions use CDT. Confirm the team's local start
time/room with the organizer; do not infer your slot from another conference session.

Ask for presentation/Q&A duration, judging criteria, deck deadline, display connectors
and venue internet. Confirm every member's registration, travel/hotel and attendance.
Carry chargers/adapters and offline materials. No registration, booking or organizer
message has been performed by the assistant.

Stop the local app before making your private backup:

```powershell
.\tasks.ps1 backup
.\tasks.ps1 verify-backup -Archive '<the ZIP path printed by backup>'
```

Restart `.\tasks.ps1 api` and rehearse. Publish the final reviewed commit if it has
not been pushed, then wait for both GitHub verification jobs to pass. Keep that exact
build for judging; repeat affected checks if you change it.
