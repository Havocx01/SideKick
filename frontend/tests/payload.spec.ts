import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

test("cold overview and first analysis loading are measurable without live AI", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  const resources = new Set<string>();
  page.on("response", response => { if (new URL(response.url()).pathname.endsWith(".js")) resources.add(response.url()); });
  const began = Date.now();
  await page.goto("/");
  await expect(page.getByText("Warnings in time", { exact: true })).toBeVisible();
  await expect(page.locator('[data-rolling-number][data-value="80"]').first()).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await page.waitForLoadState("networkidle");
  const coldRoute = [...resources];
  const overviewMs = Date.now() - began;
  await page.getByRole("link", { name: "Explore benchmark", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Model comparison", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Result details", exact: true }).click();
  const openAt = Date.now();
  await page.getByRole("button", { name: "Analyze result", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis", exact: true })).toBeVisible();
  const analysisOpenMs = Date.now() - openAt;
  await page.waitForLoadState("networkidle");
  if (process.env.SIDEKICK_PAYLOAD_OUTPUT) {
    const path = process.env.SIDEKICK_PAYLOAD_OUTPUT;
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify(coldRoute, null, 2));
    writeFileSync(`${path}.timings.json`, JSON.stringify({ overviewMs, analysisOpenMs, allJavaScript: [...resources] }, null, 2));
  }
});
