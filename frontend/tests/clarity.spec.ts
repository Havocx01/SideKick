import { expect, test } from "@playwright/test";

test("the walkthrough explains the recorded evidence without starting jobs", async ({ page }) => {
  const mutations: string[] = [];
  page.on("request", request => { if (request.method() === "POST") mutations.push(request.url()); });
  await page.goto("/");
  await page.getByRole("link", { name: "Start guided walkthrough", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Start with healthy sensors", exact: true })).toBeVisible();
  await expect(page.getByTestId("walkthrough-result")).toContainText("80 / 80");
  await page.getByRole("link", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Now make one sensor fail", exact: true })).toBeVisible();
  await expect(page.getByTestId("walkthrough-result")).toContainText("41 / 80");
  await expect(page.getByTestId("walkthrough-result")).toContainText("24");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Now make one sensor fail", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Next", exact: true }).click();
  await expect(page.getByText("Playback of stored results", { exact: true })).toBeVisible();
  const slider = page.getByRole("slider", { name: "Replay cycle" });
  const end = await slider.getAttribute("aria-valuenow");
  await page.getByRole("button", { name: "Restart playback", exact: true }).click();
  await expect(slider).toHaveAttribute("aria-valuenow", "0");
  await slider.focus();
  await page.keyboard.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuenow", "1");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await expect.poll(async () => Number(await slider.getAttribute("aria-valuenow"))).toBeGreaterThan(1);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await slider.focus();
  await page.keyboard.press("End");
  await expect(slider).toHaveAttribute("aria-valuenow", end!);
  await page.keyboard.press("ArrowLeft");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(slider).toHaveAttribute("aria-valuenow", end!);
  await expect(page.getByRole("button", { name: "Replay from start", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Next", exact: true }).click();
  await expect(page.getByTestId("walkthrough-result")).toContainText("79 / 80");
  await page.getByRole("link", { name: "Next", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ZIP", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
  expect(mutations).toEqual([]);
  await page.getByRole("link", { name: "Restart walkthrough", exact: true }).click();
  await expect(page).toHaveURL(/step=clean/);
});

test("missing measurements and incomplete coverage are explained", async ({ page }) => {
  await page.route("**/api/selection?*", async route => {
    const response = await route.fetch();
    const selection = await response.json();
    const model = selection.ranked.find((v: { config_id: string }) => v.config_id === "lr2");
    model.worst_metrics = null;
    model.clean.early_alarm_burden = null;
    model.coverage_complete = false;
    model.qualifies = false;
    await route.fulfill({ response, json: selection });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await expect(page.getByTestId("inspected-summary")).toContainText("Unavailable");
  await expect(page.getByTestId("inspected-summary")).toContainText("No required sensor-fault result is available");
  await expect(page.getByTestId("inspected-summary")).toContainText("did not cover all expected histories");
  await page.goto("/comparison?candidate=missing%2Fmodel");
  await expect(page.getByText("That candidate is unavailable in this experiment. Choose an available model.")).toBeVisible();
  await expect(page.getByTestId("inspected-summary")).toHaveCount(0);
});

for (const mode of ["demo", "replay"]) {
  test(`the walkthrough stays read-only in ${mode} mode`, async ({ page }) => {
    const mutations: string[] = [];
    page.on("request", r => { if (r.method() === "POST") mutations.push(r.url()); });
    await page.route("**/api/health", async route => {
      const response = await route.fetch();
      const health = await response.json();
      await route.fulfill({ response, json: { ...health, mode, can_upload: false, can_train: mode === "demo", can_freeze: false, can_validate: false } });
    });
    await page.goto("/walkthrough?step=clean&partition=holdout&candidate=missing");
    await expect(page.getByTestId("walkthrough-result")).toContainText("80 / 80");
    await expect(page.locator(".guide-context")).toContainText("lr2");
    await expect(page.locator(".guide-context")).toContainText("Development evidence");
    await page.getByRole("link", { name: "Next", exact: true }).click();
    await expect(page.getByTestId("walkthrough-result")).toContainText("41 / 80");
    expect(mutations).toEqual([]);
  });
}

test("the inspected result is separate from the recommendation", async ({ page }) => {
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await expect(page.getByTestId("inspected-summary")).toContainText("lr2");
  await expect(page.getByTestId("inspected-summary")).toContainText("41 / 80");
  await expect(page.getByTestId("recommendation-strip")).toContainText("aug3");
  await expect(page.locator(".guide-context")).toContainText("lr2");
  await expect(page.getByRole("group", { name: "Technical details" })).not.toBeVisible();
  await page.getByRole("button", { name: "Inspect Augmented XGBoost · aug3", exact: true }).click();
  await expect(page.getByTestId("inspected-summary")).toContainText("79 / 80");
  await expect(page.locator(".guide-context")).toContainText("aug3");
  await page.getByRole("button", { name: "Did augmented training help?", exact: true }).click();
  await page.getByRole("link", { name: "Compare configurations", exact: true }).click();
  await expect(page.getByRole("group", { name: "Technical details" })).toBeVisible();
});

test("compact results reveal explanations only when requested", async ({ page }) => {
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  const result = page.getByTestId("inspected-summary");
  await expect(result.getByRole("img", { name: "Weakest sensor fault: 41 in time, 24 late, 15 missed, out of 80 histories", exact: true })).toBeVisible();
  await expect(result).toContainText("39 fewer timely warnings");
  await expect(page.locator("#guide-answer")).toBeEmpty();
  await expect(page.getByRole("table", { name: "Worst detection by sensor and fault" })).not.toBeVisible();
  const sizes = await page.evaluate(() => ({ sidebar: document.querySelector('.sidebar')!.getBoundingClientRect().width, header: document.querySelector('.workspace-bar')!.getBoundingClientRect().height }));
  expect(sizes.sidebar).toBeLessThanOrEqual(185);
  expect(sizes.header).toBeLessThanOrEqual(60);
  const key = result.getByText("What do these numbers mean?", { exact: true });
  await key.focus();
  await page.keyboard.press("Enter");
  await expect(result.getByText(/A warning is in time when/)).toBeVisible();
  await page.getByRole("button", { name: "Why did this model pass or fail?", exact: true }).click();
  await expect(page.locator("#guide-answer")).toContainText("does not meet development criteria");
  await page.getByRole("button", { name: "Inspect Augmented XGBoost · aug3", exact: true }).click();
  await expect(page.locator(".guide-context")).toContainText("aug3");
  await expect(page.locator("#guide-answer")).toBeEmpty();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await expect(page.getByRole("link", { name: "Jump to Evidence guide" })).toBeVisible();
});

test("metric scopes and loss severity stay clear while switching models", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/comparison?candidate=xgboost_augmented%2Faug3");
  const result = page.getByTestId("inspected-summary");
  await expect(result).toContainText("equipment histories warned in time");
  await expect(result.locator(".early-alarm").filter({ hasText: "this fault" })).toContainText("0.08%");
  const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: "Inspect Augmented XGBoost · aug3", exact: true }) });
  await expect(row.getByRole("cell").nth(3)).toHaveText("0.23%");
  await expect(page.getByRole("columnheader", { name: "Worst early alarm time", exact: true })).toBeVisible();
  await expect(result.locator(".result-consequence")).toHaveText("1 fewer timely warning");
  await expect(result.locator(".warning-loss")).toHaveCount(0);

  const selector = page.getByRole("combobox", { name: "Inspect model", exact: true });
  const bounds = await selector.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThan(800);
  await selector.focus();
  await page.keyboard.press("Enter");
  const option = page.getByRole("option", { name: "Logistic regression · lr2", exact: true });
  await option.focus();
  await page.keyboard.press("Enter");
  await expect(result).toContainText("41 / 80");
  await expect(result.locator(".warning-loss")).toHaveText("39 fewer timely warnings");
  await expect(result.locator(".weakest-fault")).toContainText("Sensor 8 · Missing readings");
  await expect(page.getByTestId("recommendation-strip")).toContainText("aug3");
  await expect(page.locator(".guide-context")).toContainText("lr2");
  await expect(page.locator(".guide-question-label").filter({ hasText: "Did fault training help?" })).toBeVisible();

  const inspect = result.getByRole("link", { name: "Inspect fault", exact: true });
  const href = await inspect.getAttribute("href");
  const target = new URL(href!, "http://127.0.0.1:8136");
  expect(target.searchParams.get("candidate")).toBe("logistic_regression/lr2");
  expect(target.searchParams.get("scenario")).toMatch(/^dropout-persistent-sensor_8/);
  await inspect.click();
  await expect(page).toHaveURL(target.href);
  await expect(page.getByRole("combobox", { name: "Scenario", exact: true })).toHaveValue(/Sensor 8/);
  await expect(page.getByRole("heading", { name: "When the warning appears", exact: true })).toBeVisible();
});

test("inspect fault falls back to the matrix when the exact replay is unavailable", async ({ page }) => {
  await page.route("**/api/replay/index?*", route => route.fulfill({ json: { series: [], equipment: [], scenarios: [] } }));
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  const inspect = page.getByTestId("inspected-summary").getByRole("link", { name: "Inspect fault", exact: true });
  await expect(inspect).toHaveAttribute("href", /comparison\?candidate=logistic_regression%2Flr2&partition=out_of_fold#fault-results$/);
  await inspect.click();
  await expect(page.getByRole("table", { name: "Worst detection by sensor and fault" })).toBeVisible();
  await expect(page.locator(".guide-context")).toContainText("lr2");
});

test("replay seeks to fault onset and displays stored warning state rather than score crossings", async ({ page }) => {
  await page.route("**/api/replay?*", async route => {
    const response = await route.fetch();
    const traces = await response.json();
    for (const trace of traces) {
      trace.failure_cycle = 62;
      trace.points = [
        { cycle: 1, rul: 61, score: trace.threshold + 0.01, alert: false },
        { cycle: 2, rul: 60, score: trace.threshold + 0.01, alert: Boolean(trace.fault) },
        { cycle: 3, rul: 59, score: trace.threshold - 0.01, alert: Boolean(trace.fault) }
      ];
      trace.episodes = trace.fault ? [{ start_cycle: 2, end_cycle: 3, start_rul: 60, end_rul: 59 }] : [];
      if (trace.fault) trace.fault_onset_rul = 60;
    }
    await route.fulfill({ response, json: traces });
  });
  await page.goto("/walkthrough?step=replay");
  const state = page.getByLabel("Current replay state");
  await expect(state).toContainText("Faulted Warning active");
  await expect(page.getByRole("img", { name: "Score over time for 16", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Replay from start", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Jump to fault", exact: true }).click();
  await expect(page.getByRole("slider", { name: "Replay cycle" })).toHaveAttribute("aria-valuenow", "1");
  await expect(state).toContainText("60 cycles before failure");
  await page.getByRole("button", { name: "Restart playback", exact: true }).click();
  await expect(state).toContainText("Faulted Warning inactive");
  await page.getByText("How to read this replay", { exact: true }).click();
  await expect(page.getByText(/one threshold crossing may not activate or clear a warning/)).toBeVisible();
});
