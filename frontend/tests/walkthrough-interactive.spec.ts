import { expect, test } from "@playwright/test";

// These checks exercise the unassisted workflow. Spotlight behavior has its own tests.
test.beforeEach(async ({ page }, info) => {
  if (info.title.includes("automatically")) return;
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.guide.dismissed", "true"));
});

test("the guide starts automatically on a fresh visit and can be skipped", async ({ page }) => {
  await page.goto("/walkthrough?step=clean");
  const guide = page.getByRole("dialog", { name: "Walkthrough guide" });
  await expect(guide).toContainText("Start with the warnings");
  await guide.getByRole("button", { name: "Close guide", exact: true }).click();
  await page.getByRole("link", { name: "Next", exact: true }).click();
  await expect(page).toHaveURL(/step=fault/);
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
});

test("spotlight guides all five steps and leaves no overlay behind", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", request => { if (request.method() === "POST") posts.push(request.url()); });
  await page.goto("/walkthrough?step=clean");
  await page.getByRole("button", { name: "Show guide", exact: true }).click();
  const guide = page.getByRole("dialog", { name: "Walkthrough guide", exact: true });
  const next = guide.locator(".driver-popover-next-btn");
  await expect(guide).toContainText("Start with the warnings");
  await next.click();
  await expect(guide).toContainText("Timing matters");
  await guide.getByRole("button", { name: "Back", exact: true }).click();
  await expect(guide).toContainText("Start with the warnings");
  await next.click();
  await next.click();
  await expect(page).toHaveURL(/step=fault/);
  await expect(guide).toContainText("Try changing the readings");
  await page.getByRole("button", { name: "Healthy", exact: true }).click();
  await expect(page.getByTestId("guided-warning-result")).toContainText("80 / 80");
  await page.getByRole("button", { name: "Missing readings", exact: true }).click();
  await expect(page.getByTestId("guided-warning-result")).toContainText("41 / 80");
  await next.click();
  await expect(guide).toContainText("See which warnings survive");
  await next.click();
  await expect(guide).toContainText("Try the replay");
  await page.getByRole("button", { name: "Warning window", exact: true }).click();
  await expect(page.getByLabel("Current replay state")).toContainText("30 cycles before failure");
  const slider = page.getByRole("slider", { name: "Replay cycle" });
  await slider.focus();
  const cycle = Number(await slider.getAttribute("aria-valuenow"));
  await page.keyboard.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuenow", String(cycle + 1));
  await expect(guide).toContainText("Try the replay");
  await next.click();
  await expect(guide).toContainText("Follow the warning");
  await next.click();
  await expect(guide).toContainText("Choose what to compare");
  await page.getByRole("button", { name: "Fault tests", exact: true }).click();
  await expect(page.getByTestId("walkthrough-model-rows")).toHaveAttribute("data-emphasis", "tests");
  await next.click();
  await expect(guide).toContainText("Look beyond healthy readings");
  await next.click();
  await expect(guide).toContainText("A decision you can review");
  await next.click();
  await expect(guide).toContainText("Take the evidence with you");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download evidence", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
  await next.click();
  await expect(guide).toHaveCount(0);
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
  expect(posts).toEqual([]);
});

test("guide closes with Escape, restores focus and stays dismissed on refresh", async ({ page }) => {
  await page.goto("/walkthrough?step=clean");
  const start = page.getByRole("button", { name: "Show guide", exact: true });
  await start.click();
  await expect(page.getByRole("dialog", { name: "Walkthrough guide" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.locator(".sidekick-spotlight :focus")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(start).toBeFocused();
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
  await page.reload();
  await expect(start).toBeVisible();
  await expect(page.locator(".driver-overlay")).toHaveCount(0);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});

test("switching readings uses recorded metrics without starting jobs", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", request => { if (request.method() === "POST") posts.push(request.url()); });
  await page.goto("/walkthrough?step=fault");
  const result = page.getByTestId("guided-warning-result");
  await expect(result).toContainText("41 / 80");
  await expect(page.getByRole("button", { name: "Missing readings", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Healthy", exact: true }).click();
  await expect(result).toContainText("80 / 80");
  await expect(result).not.toContainText("41 / 80");
  await page.getByRole("button", { name: "Missing readings", exact: true }).click();
  await expect(result).toContainText("41 / 80");
  await expect(page.getByTestId("walkthrough-result")).toContainText("39 fewer timely warnings");
  await page.reload();
  await expect(result).toContainText("41 / 80");
  expect(posts).toEqual([]);
});

test("guided replay jumps to recorded milestones and pauses", async ({ page }) => {
  await page.goto("/walkthrough?step=replay");
  const slider = page.getByRole("slider", { name: "Replay cycle" });
  await page.getByRole("button", { name: "Replay from start", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Fault begins", exact: true }).click();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
  await expect(page.getByLabel("Current replay state")).toContainText("60 cycles before failure");
  await page.getByRole("button", { name: "Warning window", exact: true }).click();
  await expect(page.getByLabel("Current replay state")).toContainText("30 cycles before failure");
  await expect(page.getByTestId("replay-guidance")).toContainText("Warnings count as in time");
  await slider.focus();
  await page.keyboard.press("End");
  await expect(page.getByTestId("replay-guidance")).toContainText("too late");
});

test("comparison emphasis preserves values and the detailed table", async ({ page }) => {
  await page.goto("/walkthrough?step=compare");
  await expect(page.getByTestId("walkthrough-model-rows")).toContainText("79 / 80");
  await page.getByRole("button", { name: "Fault tests", exact: true }).click();
  await expect(page.getByTestId("walkthrough-model-rows")).toHaveAttribute("data-emphasis", "tests");
  await expect(page.getByTestId("walkthrough-model-rows")).toContainText("64 / 64");
  await page.getByText("Detailed comparison", { exact: true }).click();
  await expect(page.getByRole("table", { name: "Recorded model comparison" })).toContainText("79 / 80");
  await expect(page.getByTestId("walkthrough-result")).toContainText("does not prove augmented training helped");
});

test("missing fault metrics only disable the fault switch", async ({ page }) => {
  await page.route("**/api/selection?*", async route => {
    const response = await route.fetch();
    const selection = await response.json();
    selection.ranked.find((model: { config_id: string }) => model.config_id === "lr2").worst_metrics = null;
    await route.fulfill({ response, json: selection });
  });
  await page.goto("/walkthrough?step=fault");
  await expect(page.getByTestId("guided-warning-result")).toContainText("80 / 80");
  await expect(page.getByRole("button", { name: "Missing readings", exact: true })).toBeDisabled();
  await expect(page.getByText("Fault measurements are unavailable. Healthy readings are still shown.")).toBeVisible();
});

test("the report offers named actions and scoped evidence", async ({ page }) => {
  await page.goto("/walkthrough?step=report");
  await expect(page.getByRole("link", { name: "Open report", exact: true })).toHaveAttribute("href", /candidate=xgboost_augmented%2Faug3.*partition=out_of_fold/);
  await expect(page.getByTestId("walkthrough-report-preview")).toContainText("Fresh validation required");
  const document = await page.request.get((await page.getByRole("link", { name: "Open report", exact: true }).getAttribute("href"))!);
  expect(document.ok()).toBe(true);
  expect(await document.text()).toContain("Engineering decision report");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download evidence", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
});

test("missing replay milestones disable only the affected controls", async ({ page }) => {
  await page.route("**/api/replay?*", async route => {
    const response = await route.fetch();
    const traces = await response.json();
    for (const trace of traces) {
      trace.fault_onset_rul = null;
      trace.points = trace.points.filter((point: { rul: number }) => point.rul > 30);
    }
    await route.fulfill({ response, json: traces });
  });
  await page.goto("/walkthrough?step=replay");
  await expect(page.getByRole("button", { name: "Fault begins", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Warning window", exact: true })).toBeDisabled();
  await expect(page.getByRole("slider", { name: "Replay cycle" })).toBeEnabled();
  await expect(page.getByText("No stored reading falls inside the warning window.", { exact: false })).toBeVisible();
});

test("reduced motion preserves manual replay and unrestricted navigation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/walkthrough?step=replay");
  await expect(page.getByRole("button", { name: "Replay from start", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Warning window", exact: true }).click();
  await expect(page.getByLabel("Current replay state")).toContainText("30 cycles before failure");
  await page.getByRole("link", { name: "Next", exact: true }).click();
  await page.goBack();
  await expect(page).toHaveURL(/step=replay/);
  await expect(page.getByRole("button", { name: /^(Play|Replay from start)$/ })).toBeDisabled();
});

for (const theme of ["light", "dark"]) {
  test(`mobile spotlight fits the screen in ${theme} theme`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(value => localStorage.setItem("sidekick-theme", value), theme);
    await page.goto("/walkthrough?step=clean");
    await page.getByRole("button", { name: "Show guide", exact: true }).click();
    const guide = page.getByRole("dialog", { name: "Walkthrough guide" });
    await expect(guide).toBeVisible();
    await guide.locator(".driver-popover-next-btn").click();
    await expect(guide).toContainText("Timing matters");
    const bounds = await guide.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
    expect(bounds!.y).toBeGreaterThanOrEqual(0);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(844);
    await guide.getByRole("button", { name: "Close guide", exact: true }).click();
    await page.getByRole("link", { name: "5 Report", exact: true }).click();
    await expect(page.getByRole("button", { name: "Download evidence", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
