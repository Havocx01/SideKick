import { expect, test } from "@playwright/test";

test("an assessment opens its exact cited fault and reuses evidence in a review", async ({ page }) => {
  const mutations: string[] = [];
  page.on("request", request => { if (request.method() === "POST") mutations.push(new URL(request.url()).pathname); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  const assessment = page.getByRole("region", { name: "Assessment", exact: true });
  await expect(assessment).toContainText("39 fewer timely warnings");
  const citation = assessment.getByRole("link", { name: "Histories warned in time: 41" });
  expect(await citation.getAttribute("href")).toContain("scenario=");
  await citation.click();
  await expect(page.getByRole("region", { name: "Scenario details" })).toContainText("Detection below minimum");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  await page.getByRole("button", { name: "Add to review brief", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Review brief", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/39 fewer timely warnings/);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export brief", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
  expect(mutations.every(path => path.startsWith("/api/assistant/"))).toBeTruthy();
});

test("data review explains missing failure confirmation and applies a draft only", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", request => { if (request.method() === "POST") requests.push(new URL(request.url()).pathname); });
  const csv = ["equipment_id,cycle,sensor_1", ...Array.from({ length: 30 }, (_, engine) =>
    Array.from({ length: 120 }, (_, i) => `${engine + 1},${i + 1},${(i / 120 + engine / 30).toFixed(3)}`)).flat()].join("\n");
  await page.goto("/new?source=upload");
  await page.getByLabel("CSV file (up to 10 MB)").setInputFiles({ name: "practice.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Review data", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Data review", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toContainText("Confirm that every history reaches failure");
  await page.getByRole("button", { name: "Use draft mapping", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /I confirm every equipment history/ })).not.toBeChecked();
  await expect(page.getByRole("button", { name: "Validate and confirm mapping", exact: true })).toBeDisabled();
  expect(requests.every(path => path === "/api/datasets/upload" || path === "/api/assistant/analyses")).toBeTruthy();
});

for (const theme of ["light", "dark"]) {
  test(`investigation fits mobile in ${theme} theme`, async ({ page }, testInfo) => {
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    if (await page.locator("html").getAttribute("data-theme") !== theme) await page.getByRole("switch").first().click();
    await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Analysis", exact: true });
    await expect(dialog.getByRole("region", { name: "Assessment", exact: true })).toBeVisible();
    expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`investigation-${theme}-mobile.png`) });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Investigate failure", exact: true })).toBeFocused();
  });
}
