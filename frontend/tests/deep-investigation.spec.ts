import { expect, test, type Page } from "@playwright/test";
import type { AnalysisRecord, AnalysisRequest, DeepReport } from "../src/api/types";

async function launch(page: Page) {
  await page.getByRole("button", { name: "Deep investigation", exact: true }).click();
  await page.getByRole("dialog", { name: "Plan an investigation", exact: true }).getByRole("button", { name: "Start investigation", exact: true }).click();
}

async function fixture(page: Page, allowed = true) {
  const response = await page.request.post("/api/assistant/analyses", { headers: { "X-Sidekick-Request": "1" }, data: { task: "investigate", candidates: ["logistic_regression/lr2"] } });
  expect(response.ok()).toBeTruthy();
  const seed = await response.json() as AnalysisRecord;
  const observation = { id: "pattern-a", title: "Logistic regression · Sensor 8 · dropout", text: "Recorded dropout cases have fewer timely warnings than healthy readings.", source_ids: seed.result!.sources.slice(0, 3).map(source => source.id) };
  const report: DeepReport = { summary: "Missing readings deserve a targeted check before retesting.",
    hypotheses: [{ title: "Missingness handling may mask useful changes", explanation: "Median imputation may hide changes used by the warning model.", alternative: "The warning threshold may also explain the missed window.", observation_ids: [observation.id] }],
    gaps: ["Aggregate counts do not identify which histories missed a warning."],
    next_tests: [{ title: "Audit missingness and replay warning timing", procedure: "Check missing-reading flags and median imputation; inspect late and missed warnings with the model fixed.", expected_signal: "Warnings recover when missingness is represented explicitly.", interpretation: "Recovery would support a handling issue; no recovery would shift attention to timing.", observation_ids: [observation.id], model: "Logistic regression (lr2)", check_type: "score_persistence", focus: "Do scores cross the threshold without sustaining a warning?", readiness: "needs_evidence", prerequisites: ["Obtain matched clean/faulted development warning summaries for this model."], controls: ["Keep the model and alert rules fixed."] }],
    observations: [observation, { id: "history-summary-1", kind: "supporting", title: "Paired warning history", text: "Clean: timely; faulted: late. Stored examples are selected, not representative equipment samples.", source_ids: observation.source_ids }], inspected_cases: 64, pattern_count: 1, latency_seconds: .2, request_count: 1,
    limitations: ["Hypotheses require engineer review.", "No new tests were run."] };
  let record: AnalysisRecord = { ...seed, context: { ...seed.context, task: "deep" }, result: { ...seed.result!, mode: "ai", model: "fixture", deep_report: report } };
  const state = { allowed, starts: 0, reads: 0, cancels: 0, conversions: 0, running: false, cancelled: false, fail: false, permissionFailure: false, report, contextSaves: 0, contextFailure: false, fields: { equipment_type: "", sensor_meaning: "", decision: "" }, contexts: [] as AnalysisRequest[] };
  await page.route("**/api/assistant/experiment-context*", async route => {
    if (route.request().method() === "POST") {
      state.contextSaves++;
      if (state.contextFailure) return route.fulfill({ status: 503, json: { detail: "Context could not be saved. Try again." } });
      const draft = route.request().postDataJSON();
      state.fields = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, String(value).trim()])) as typeof state.fields;
    }
    await route.fulfill({ json: state.fields });
  });
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.route("**/api/assistant/capabilities*", route => route.fulfill({ json: { tasks: ["investigate", "compare", "warning", "brief", "deep"], live_available: false, deep_available: true, unlock_available: false, unlocked: true, consent_required: true, consent_granted: state.allowed, mode: "full", note: "Offline fixture" } }));
  await page.route("**/api/assistant/consent/workspace", async route => {
    if (route.request().method() === "POST") {
      if (state.permissionFailure) return route.fulfill({ status: 503, json: { detail: "Permission could not be saved." } });
      state.allowed = route.request().postDataJSON().allowed;
    }
    await route.fulfill({ json: { experiment_id: "workspace", allowed: state.allowed, disclosure: "Aliased recorded patterns only." } });
  });
  const output = () => ({ ...record, status: state.cancelled ? "cancelled" : state.running ? "running" : "completed", output_currency: "current", result: state.fail ? { ...seed.result!, fallback_reason: "Live analysis failed verification. Showing recorded evidence." } : record.result });
  await page.route(/\/api\/assistant\/analyses(?:\?.*)?$/, async route => {
    state.starts++;
    const body = route.request().postDataJSON() as AnalysisRequest;
    expect(body.task).toBe("deep");
    state.contexts.push(body);
    record = { ...record, context: { ...record.context, ...body } };
    await route.fulfill({ json: output() });
  });
  await page.route(new RegExp(`/api/assistant/analyses/${seed.id}(?:/.*)?$`), async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/cancel")) { state.cancels++; state.running = false; state.cancelled = true; }
    if (path.endsWith("/review")) {
      state.conversions++;
      record = { ...record, context: { ...record.context, task: "brief" }, result: { ...record.result!, brief_draft: "Engineer review draft\nPossible explanations\nMissingness handling may mask useful changes\nNext tests\nAudit missing-reading flags and median imputation." } };
    }
    if (path.endsWith("/brief")) record = { ...record, brief_text: route.request().postDataJSON().text, brief_saved_at: route.request().postDataJSON().draft_only ? null : 200 };
    if (route.request().method() === "GET") state.reads++;
    await route.fulfill({ json: output() });
  });
  return state;
}

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`checked question with no retained explanation is honest at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    const state = await fixture(page);
    state.report.hypotheses = [];
    state.report.limitations.push("No AI explanation passed verification.");
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    await launch(page);
    const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
    await expect(dialog.getByText("No AI explanation passed verification.", { exact: false }).first()).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Leading hypothesis", exact: false })).toHaveCount(0);
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Collect evidence first");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Obtain matched clean/faulted");
    expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath("checked-question.png"), animations: "disabled" });
    expect(state.starts).toBe(1);
  });
}

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`deep report reopens and converts without regeneration at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    const state = await fixture(page);
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    await page.getByRole("button", { name: "Deep investigation", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "Plan an investigation" });
    await setup.getByText("Experiment context · Optional", { exact: true }).click();
    await page.getByRole("textbox", { name: "Equipment type", exact: true }).fill(" Cooling pump ");
    await page.getByRole("textbox", { name: "What the sensors measure", exact: true }).fill("Bearing temperature");
    await page.getByRole("textbox", { name: "Decision the experiment supports", exact: true }).fill("Investigate missing warnings");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    await setup.getByRole("button", { name: "Save context", exact: true }).click();
    await expect(setup.getByRole("status").filter({ hasText: "Context saved" })).toBeVisible();
    expect(state.starts).toBe(0);
    await setup.getByRole("button", { name: "Start investigation", exact: true }).click();
    await expect.poll(() => state.contexts[0]?.engineer_context).toEqual({ equipment_type: "Cooling pump", sensor_meaning: "Bearing temperature", decision: "Investigate missing warnings" });
    const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
    await expect(dialog.getByRole("region", { name: "Possible explanations" })).toContainText("Alternative:");
    await expect(dialog.getByRole("heading", { name: "Leading hypothesis", exact: false })).toBeVisible();
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Check missing-reading flags and median imputation");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Collect evidence first");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Obtain matched clean/faulted development warning summaries");
    await dialog.getByText("How to interpret this check", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("What it would mean");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Keep the model and alert rules fixed.");
    await dialog.getByRole("region", { name: "Possible explanations" }).getByText("Recorded evidence (1 pattern)", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(dialog.getByText("Recorded dropout cases have fewer timely warnings than healthy readings.", { exact: true }).first()).toBeVisible();
    const patternPanel = dialog.locator("details").filter({ has: page.locator("summary", { hasText: "All inspected patterns" }) });
    await patternPanel.locator("summary").click();
    await expect(patternPanel.locator("article").first()).toBeVisible();
    const inset = await patternPanel.locator("article").first().evaluate(node => {
      const panel = node.closest("details")!.getBoundingClientRect();
      const text = node.getBoundingClientRect();
      return { left: text.left - panel.left, right: panel.right - text.right };
    });
    expect(inset.left).toBeGreaterThanOrEqual(16);
    expect(inset.right).toBeGreaterThanOrEqual(16);
    await patternPanel.locator("summary").click();
    expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await dialog.getByText("Additional recorded inputs", { exact: false }).click();
    await expect(dialog.getByText("Clean: timely; faulted: late. Stored examples are selected, not representative equipment samples.", { exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`deep-${theme}-${width}.png`), animations: "disabled" });
    await dialog.getByRole("button", { name: "Close analysis" }).click();
    await expect(page.getByRole("button", { name: "Deep investigation", exact: true })).toBeFocused();
    await launch(page);
    await expect(dialog.getByRole("region", { name: "Possible explanations" })).toBeVisible();
    expect(state.starts).toBe(1); expect(state.reads).toBeGreaterThan(0); expect(state.cancels).toBe(0);
    await dialog.getByRole("button", { name: "Add to review brief", exact: true }).click();
    const brief = page.getByRole("dialog", { name: "Review brief", exact: true });
    await expect(brief.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/Possible explanations/);
    expect(state.conversions).toBe(1); expect(state.starts).toBe(1);
  });
}

test("main finding follows the priority check and supporting detail stays accessible", async ({ page }) => {
  const state = await fixture(page);
  state.report.hypotheses.unshift({ title: "A secondary possible explanation", explanation: "A different mechanism may explain other patterns.", alternative: "Input handling could also differ.", observation_ids: ["pattern-secondary"] });
  state.report.observations.push({ id: "pattern-secondary", title: "A secondary recorded pattern", text: "Supporting observation remains available.", source_ids: [] });
  state.report.next_tests.push({ ...state.report.next_tests[0], title: "Inspect the secondary pattern", observation_ids: ["pattern-secondary"] });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await launch(page);
  const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
  const finding = dialog.getByRole("region", { name: "Possible explanations", exact: true });
  await expect(finding).toContainText("Missingness handling may mask useful changes");
  await expect(finding).not.toContainText("A secondary possible explanation");
  const order = await dialog.evaluate(node => {
    const main = node.querySelector('.deep-main-finding')!;
    const check = node.querySelector('.deep-priority-check')!;
    const details = node.querySelector('.deep-supporting-details')!;
    return Boolean(main.compareDocumentPosition(check) & Node.DOCUMENT_POSITION_FOLLOWING)
      && Boolean(check.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(order).toBeTruthy();
  await expect(dialog.getByRole("heading", { name: "A secondary possible explanation", exact: true })).not.toBeVisible();
  await dialog.getByText("Other possible explanations (1)", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("heading", { name: "A secondary possible explanation", exact: true })).toBeVisible();
  await dialog.getByText("Additional checks (1)", { exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "Inspect the secondary pattern", exact: true })).toBeVisible();
  await dialog.getByText("What remains uncertain", { exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Evidence gaps" })).toContainText("Aggregate counts");
  expect(state.starts).toBe(1);
});

test("deep permission is deliberate, failure retains the action, routine analysis stays local", async ({ page }) => {
  const state = await fixture(page, false);
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await launch(page);
  const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
  await expect(dialog.getByRole("region", { name: "Deep investigation permission" })).toBeVisible();
  expect(state.starts).toBe(0);
  state.permissionFailure = true;
  await dialog.getByRole("button", { name: "Enable AI and investigate", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Permission could not be saved.");
  expect(state.starts).toBe(0);
  state.permissionFailure = false;
  await dialog.getByRole("button", { name: "Enable AI and investigate", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Possible explanations" })).toBeVisible();
  expect(state.starts).toBe(1);
});

test("deep work hides output while running, survives close, and offers explicit failure retry", async ({ page }) => {
  const state = await fixture(page);
  state.running = true;
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await launch(page);
  const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
  await expect(dialog.getByRole("region", { name: "Analysis progress" })).toBeVisible();
  await expect(dialog.locator(".deep-report")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close analysis" }).click();
  await launch(page);
  expect(state.starts).toBe(1); expect(state.cancels).toBe(0);
  state.running = false; state.fail = true;
  await expect(dialog.getByRole("alert")).toContainText("failed verification");
  await expect(dialog.getByRole("button", { name: "Recorded evidence ready", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Retry analysis", exact: true })).toBeVisible();
  expect(state.starts).toBe(1);
  state.running = true; state.fail = false;
  await dialog.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Cancel analysis", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel analysis", exact: true }).click();
  await expect(dialog.getByRole("region", { name: "Analysis status" })).toContainText("Analysis cancelled");
  expect(state.cancels).toBe(1); expect(state.starts).toBe(2);
});

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`context stays out of action row; setup saves locally at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    const state = await fixture(page);
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    await expect(page.getByText("Engineer context (optional)", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Deep investigation", exact: true }).click();
    const setup = page.getByRole("dialog", { name: "Plan an investigation", exact: true });
    await expect(setup.getByRole("button", { name: "Start investigation", exact: true })).toBeEnabled();
    expect(state.starts).toBe(0);
    await page.screenshot({ path: testInfo.outputPath("investigation-setup.png"), animations: "disabled" });
    await setup.getByText("Experiment context · Optional", { exact: true }).click();
    await setup.getByRole("textbox", { name: "Equipment type", exact: true }).fill("Cooling pump");
    await setup.getByRole("textbox", { name: "What the sensors measure", exact: true }).fill("Bearing temperature");
    await setup.getByRole("textbox", { name: "Decision the experiment supports", exact: true }).fill("Review warning delays");
    state.contextFailure = true;
    await setup.getByRole("button", { name: "Save context", exact: true }).click();
    await expect(setup.getByRole("alert")).toContainText("Context could not be saved");
    await expect(setup.getByRole("textbox", { name: "Equipment type", exact: true })).toHaveValue("Cooling pump");
    await expect(setup.getByRole("button", { name: "Start investigation", exact: true })).toBeDisabled();
    expect(state.starts).toBe(0);
    state.contextFailure = false;
    await setup.getByRole("button", { name: "Save context", exact: true }).click();
    await expect(setup.getByRole("status")).toContainText("Context saved");
    await setup.getByRole("textbox", { name: "What should this investigation focus on? (optional)", exact: true }).fill("Compare score response and persistence");
    expect(await setup.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await setup.getByRole("button", { name: "Start investigation", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Deep investigation", exact: true }).getByRole("region", { name: "Possible explanations" })).toBeVisible();
    expect(state.starts).toBe(1);
    expect(state.contexts[0].investigation_focus).toBe("Compare score response and persistence");
    expect(state.contexts[0].engineer_context?.equipment_type).toBe("Cooling pump");
  });
}

test("abstention is distinguished from a rejected explanation", async ({ page }) => {
  const state = await fixture(page);
  state.report.hypotheses = [];
  state.report.explanation_status = "abstained";
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await launch(page);
  const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
  await expect(dialog).toContainText("AI did not propose an explanation from the available evidence.");
  await expect(dialog).not.toContainText("No AI explanation passed verification.");
});


for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`recorded facts stay separate from hypotheses and missing evidence at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    const state = await fixture(page);
    const stored = state.report.observations.find(item => item.id === "history-summary-1")!;
    stored.summary = "Same recorded history: clean timely → faulted missed. Scores met the threshold briefly; the recorded warning remained inactive. This selected history does not establish a cause.";
    stored.text = "Clean: timely; faulted: missed. Stored examples are selected, not representative equipment samples.";
    stored.related_pattern_ids = ["pattern-a"];
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    await launch(page);
    const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
    const facts = dialog.getByRole("region", { name: "Recorded facts", exact: true });
    await expect(facts).toContainText("clean timely → faulted missed");
    await expect(facts).not.toContainText("Median imputation may");
    await expect(dialog.getByRole("region", { name: "Possible explanations" })).toContainText("Possible explanation · Needs checking");
    await expect(dialog.getByRole("region", { name: "Proposed next tests" })).toContainText("Needed before this check");
    await facts.getByText("Recorded evidence (1 record)", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(facts.getByRole("heading", { name: "Paired warning history", exact: true, level: 4 })).toBeVisible();
    expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath("facts-hypothesis.png"), animations: "disabled" });
    expect(state.starts).toBe(1);
  });
}
