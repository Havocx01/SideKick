import type { ExperimentEngineerContext, ExperimentRecord, PilotBrief } from "../api/types";

export const DEMO_INVESTIGATION_FOCUS = "Which sensor faults most reduce timely warnings, and what evidence should we inspect next?";

type DemoRun = Pick<ExperimentRecord, "name" | "source" | "config" | "pilot_brief">;

// Only the prepared presentation files opt in. Ordinary uploads and the built-in
// synthetic sample keep their existing blank/default forms.
export function demoPrefill(run: DemoRun) {
  if (run.source !== "upload" || !/^(sidekick-demo-fresh(?:-\d+)?|sidekick-fresh-synthetic-20261013)\.csv$/i.test(run.name)) return null;
  const config = run.config;
  const number = (key: string) => typeof config[key] === "number" && Number.isFinite(config[key]) ? config[key] as number : null;
  const detection = number("min_detection_fraction"), burden = number("max_early_alarm_burden");
  const lead = number("min_useful_lead"), horizon = number("horizon_cycles");
  const success = detection !== null && burden !== null && lead !== null && horizon !== null
    ? `At least ${Number((detection * 100).toFixed(2))}% timely warnings within ${lead}–${horizon} cycles before failure, no more than ${Number((burden * 100).toFixed(2))}% early-alarm time, and complete coverage across all required fault cases.`
    : "Meet the recorded warning, early-alarm and coverage limits across all required fault cases.";
  const context: ExperimentEngineerContext = {
    equipment_type: "Simulated equipment — Sidekick demo",
    sensor_meaning: "Simulated bearing-temperature, vibration, and outlet-pressure readings. These are not field measurements.",
    decision: "Decide whether this model merits further testing with representative equipment data."
  };
  const brief: PilotBrief = {
    equipment_family: context.equipment_type,
    reviewing_engineer: "Kareem Massoud — demo reviewer",
    current_procedure: "Review healthy-sensor results, then inspect how sensor faults affect the warnings.",
    intended_decision: context.decision,
    success_measure: success,
    data_classification: "simulated"
  };
  return {
    context, brief, focus: DEMO_INVESTIGATION_FOCUS,
    reviewReason: "These results use simulated histories. Collect representative equipment data and agree equipment-specific test settings before considering a site trial."
  };
}

export function prefillPilotBrief(existing: PilotBrief | null | undefined, defaults: PilotBrief): PilotBrief {
  const result = { ...existing };
  for (const key of ["equipment_family", "reviewing_engineer", "current_procedure", "intended_decision", "success_measure"] as const) {
    if (!result[key]?.trim()) result[key] = defaults[key];
  }
  if (!result.data_classification || result.data_classification === "unverified") result.data_classification = defaults.data_classification;
  return result;
}

export function prefillEngineerContext(existing: ExperimentEngineerContext, defaults: ExperimentEngineerContext): ExperimentEngineerContext {
  return {
    equipment_type: existing.equipment_type?.trim() ? existing.equipment_type : defaults.equipment_type,
    sensor_meaning: existing.sensor_meaning?.trim() ? existing.sensor_meaning : defaults.sensor_meaning,
    decision: existing.decision?.trim() ? existing.decision : defaults.decision
  };
}
