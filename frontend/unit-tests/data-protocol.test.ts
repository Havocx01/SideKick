import { strict as assert } from "node:assert";
import { test } from "node:test";
import { createMemoryRouter } from "react-router-dom";
import { protocolSearch, protocolTiming, protocolView, splitIntegrity } from "../src/lib/dataProtocol.ts";

const recorded = { min_useful_lead: 10, horizon_cycles: 30, late_window_end: 9, transition_band_end: 45 };

test("recorded scoring boundaries include useful endpoints and exclude the transition band", () => {
  const result = protocolTiming(recorded);
  assert.equal(result.available, true);
  assert.deepEqual(result.zones.map(zone => zone.range), ["46+", "31–45", "10–30", "1–9"]);
  assert.equal(result.gap, null);
  assert.match(result.zones[1]!.explanation, /excluded from early-alarm burden/);
  assert.match(result.zones[2]!.explanation, /active/);
});

test("custom settings and an uncovered interval remain explicit", () => {
  const result = protocolTiming({ min_useful_lead: 6, horizon_cycles: 18, late_window_end: 3, transition_band_end: 25 });
  assert.deepEqual(result.zones.map(zone => zone.range), ["26+", "19–25", "6–18", "1–3"]);
  assert.equal(result.gap, "4–5");
});

test("missing, non-finite, fractional and inconsistent settings do not acquire demo defaults", () => {
  for (const settings of [{}, { ...recorded, late_window_end: undefined }, { ...recorded, min_useful_lead: NaN },
    { ...recorded, min_useful_lead: 10.5 }, { ...recorded, transition_band_end: 30 }, { ...recorded, late_window_end: 10 }]) {
    const result = protocolTiming(settings);
    assert.equal(result.available, false);
    assert.deepEqual(result.zones, []);
  }
});

test("a recorded empty late window does not imply late warnings are scored", () => {
  const result = protocolTiming({ ...recorded, late_window_end: 0 });
  assert.equal(result.available, true);
  assert.equal(result.zones[3]!.range, "None");
  assert.equal(result.gap, "1–9");
});

test("tabs have a safe default without confusing evidence partition with page view", () => {
  assert.equal(protocolView("sensors"), "sensors");
  assert.equal(protocolView("technical"), "technical");
  assert.equal(protocolView("holdout"), "overview");
  assert.equal(protocolView(null), "overview");
});

test("partition assignment checks detect overlap and repeated equipment", () => {
  assert.equal(splitIntegrity({ development: ["a", "b"], holdout: ["c"] }), null);
  assert.match(splitIntegrity({ development: ["a"], holdout: ["a"] })!, /both/);
  assert.match(splitIntegrity({ development: ["a", "a"], holdout: [] })!, /repeated/);
  assert.equal(splitIntegrity({ development: [], holdout: [] }), null);
});

test("tab navigation preserves evidence context and router Back restores the previous view", async () => {
  const path = "/experiments/fixture/data";
  const original = new URLSearchParams({ candidate: "logistic_regression/lr2", partition: "holdout", experiment_id: "fixture", view: "overview" });
  const router = createMemoryRouter([{ path: "*" }], { initialEntries: [`${path}?${original}`] });
  try {
    for (const view of ["sensors", "technical"]) {
      await router.navigate({ search: protocolSearch(new URLSearchParams(router.state.location.search), view).toString() });
      const query = new URLSearchParams(router.state.location.search);
      assert.equal(query.get("candidate"), original.get("candidate"));
      assert.equal(query.get("partition"), "holdout");
      assert.equal(query.get("experiment_id"), "fixture");
      assert.equal(query.get("view"), view);
      assert.equal(router.state.location.pathname, path);
    }
    await router.navigate(-1);
    assert.equal(protocolView(new URLSearchParams(router.state.location.search).get("view")), "sensors");
    await router.navigate(-1);
    assert.equal(protocolView(new URLSearchParams(router.state.location.search).get("view")), "overview");
    assert.equal(original.get("view"), "overview", "query updates never mutate their input");
  } finally { router.dispose(); }
});
