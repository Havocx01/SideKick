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
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
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
  await expect(page.getByText("That candidate is unavailable in this experiment. Select an available model below to inspect it.")).toBeVisible();
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
  await page.getByRole("row", { name: "Inspect Augmented XGBoost · aug3", exact: true }).click();
  await expect(page.getByTestId("inspected-summary")).toContainText("79 / 80");
  await expect(page.locator(".guide-context")).toContainText("aug3");
  await page.getByRole("button", { name: "Did augmented training help?", exact: true }).click();
  await page.getByRole("link", { name: "Compare configurations", exact: true }).click();
  await expect(page.getByRole("group", { name: "Technical details" })).toBeVisible();
});
