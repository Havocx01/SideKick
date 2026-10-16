import { strict as assert } from "node:assert";
import { test } from "node:test";
import { demoPrefill, prefillEngineerContext, prefillPilotBrief } from "../src/lib/demo-prefill.ts";

const run = {
  name: "Sidekick-Demo-Fresh.csv", source: "upload" as const, pilot_brief: null,
  config: { min_detection_fraction: .7, max_early_alarm_burden: .1, min_useful_lead: 10, horizon_cycles: 30 }
};

test("only the prepared demo filenames opt in", () => {
  for (const name of [run.name, "Sidekick-Demo-Fresh-2.csv", "sidekick-fresh-synthetic-20261013.csv"]) assert.ok(demoPrefill({ ...run, name }));
  for (const name of ["equipment.csv", "sidekick-synthetic-test.csv", "Synthetic equipment sample", "Sidekick-Demo-Fresh.csv.backup"]) assert.equal(demoPrefill({ ...run, name }), null);
  assert.equal(demoPrefill({ ...run, source: "synthetic" }), null);
});

test("success text uses the run's recorded limits rather than fixed demo numbers", () => {
  const result = demoPrefill({ ...run, config: { min_detection_fraction: .85, max_early_alarm_burden: .025, min_useful_lead: 15, horizon_cycles: 40 } })!;
  assert.match(result.brief.success_measure!, /85%.*15–40.*2.5%/);
  assert.equal(result.brief.data_classification, "simulated");
});

test("missing settings do not invent numeric criteria", () => {
  assert.doesNotMatch(demoPrefill({ ...run, config: {} })!.brief.success_measure!, /70|10|30/);
});

test("existing pilot text and explicit data classification are preserved", () => {
  const existing = { reviewing_engineer: "Adam", intended_decision: "Check this bearing", data_classification: "field" as const };
  const filled = prefillPilotBrief(existing, demoPrefill(run)!.brief);
  assert.equal(filled.reviewing_engineer, "Adam");assert.equal(filled.intended_decision, "Check this bearing");
  assert.equal(filled.data_classification, "field");assert.ok(filled.equipment_family);
  assert.equal(existing.reviewing_engineer, "Adam");
});

test("context fills blank descriptions without replacing a saved description", () => {
  const filled = prefillEngineerContext({ equipment_type: "Existing family", sensor_meaning: " ", decision: "" }, demoPrefill(run)!.context);
  assert.equal(filled.equipment_type, "Existing family");assert.match(filled.sensor_meaning!, /Simulated/);assert.ok(filled.decision);
});
