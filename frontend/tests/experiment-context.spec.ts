import { expect, test } from "@playwright/test";
import type { ExperimentCreate } from "../src/api/types";

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`Pilot brief supplies shared context without launching training at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    let admitted: ExperimentCreate | undefined;
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => {
      localStorage.setItem("sidekick-theme", theme);
      sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true");
    }, theme);
    await page.route(/\/api\/experiments$/, async route => {
      if (route.request().method() !== "POST") return route.continue();
      admitted = route.request().postDataJSON();
      await route.fulfill({ status: 409, json: { detail: "Fixture stopped before training; no job was launched." } });
    });
    await page.goto("/new?source=sample");
    await page.getByRole("button", { name: "Generate sample data", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Review the test", exact: true })).toBeVisible();
    await page.getByText("Pilot brief (optional)", { exact: true }).click();
    await page.getByRole("textbox", { name: "Equipment type", exact: true }).fill("Cooling pump");
    await page.getByRole("textbox", { name: "What the sensors measure", exact: true }).fill("Bearing temperature and outlet pressure");
    await page.getByRole("textbox", { name: "Decision this review supports", exact: true }).fill("Review delayed warnings");
    await page.getByRole("textbox", { name: "Reviewing engineer", exact: true }).fill("Private contact not shared with AI");
    await expect(page.getByText("Equipment type, sensor meaning and decision are saved for AI investigations.", { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath("pilot-context.png"), fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: "Train and challenge models", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Fixture stopped before training" })).toBeVisible();
    expect(admitted?.engineer_context).toEqual({ equipment_type: "Cooling pump", sensor_meaning: "Bearing temperature and outlet pressure", decision: "Review delayed warnings" });
    expect(JSON.stringify(admitted?.engineer_context)).not.toContain("Private contact");
    await expect(page.getByRole("textbox", { name: "What the sensors measure", exact: true })).toHaveValue("Bearing temperature and outlet pressure");
  });
}
