import { expect, test, type Page } from "@playwright/test";
import type { ConsentState } from "../src/api/types";

async function permissionFixture(page: Page) {
  const fixture = { allowed: false, fail: false, saves: 0 };
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.route("**/api/assistant/capabilities*", route => route.fulfill({ json: {
    tasks: ["investigate", "compare", "warning", "brief", "data"], mode: "full", live_available: fixture.allowed,
    unlocked: true, unlock_available: false, consent_required: true, consent_granted: fixture.allowed, note: "Fixture only",
  } }));
  await page.route("**/api/assistant/consent/**", async route => {
    expect(new URL(route.request().url()).pathname).toBe("/api/assistant/consent/workspace");
    if (route.request().method() === "POST") {
      expect(route.request().headers()["x-sidekick-request"]).toBe("1");
      if (fixture.fail) return route.fulfill({ status: 503, json: { detail: "Permission could not be saved." } });
      fixture.allowed = route.request().postDataJSON().allowed; fixture.saves++;
    }
    await route.fulfill({ json: { experiment_id: "workspace", allowed: fixture.allowed,
      disclosure: "Fixture disclosure for all existing and future local experiments." } satisfies ConsentState });
  });
  return fixture;
}

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`workspace permission persists, retains failed saves and fits ${width}px in ${theme}`, async ({ page }) => {
    const fixture = await permissionFixture(page);
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/");
    const opener = page.getByRole("button", { name: "AI settings", exact: true });
    await opener.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Workspace AI", exact: true });
    await expect(dialog.getByRole("heading")).toBeFocused();
    await expect(dialog).toContainText("all existing and future experiments");
    await dialog.getByRole("button", { name: "Enable AI analysis", exact: true }).click();
    await expect(dialog).toContainText("AI is enabled.");
    expect(fixture.saves).toBe(1);
    const bounds = (await dialog.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(844);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `../output/playwright/workspace-ai-${theme}-${width}.png` });
    await page.keyboard.press("Escape"); await expect(opener).toBeFocused();
    await page.reload(); await opener.click();
    await expect(dialog).toContainText("AI is enabled.");
    fixture.fail = true;
    await dialog.getByRole("button", { name: "Turn off AI analysis" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Permission could not be saved.");
    await expect(dialog).toContainText("AI is enabled.");
    fixture.fail = false;
    await dialog.getByRole("button", { name: "Turn off AI analysis" }).click();
    await expect(dialog).toContainText("AI is off.");
    await expect(dialog.getByRole("alert")).toHaveCount(0);
  });
}

test("one approval upgrades the analysis and later contexts do not request approval again", async ({ page }) => {
  const fixture = await permissionFixture(page);
  let starts = 0;
  await page.route(/\/api\/assistant\/analyses(?:\?.*)?$/, async route => {
    starts++;
    const response = await route.fetch();
    const record = await response.json();
    if (fixture.allowed) record.result = { ...record.result, mode: "ai", fallback_reason: null };
    await route.fulfill({ response, json: record });
  });
  await page.route("**/api/assistant/analyses/*", async route => {
    const response = await route.fetch();
    const record = await response.json();
    if (fixture.allowed && record.result) record.result = { ...record.result, mode: "ai", fallback_reason: null };
    await route.fulfill({ response, json: record });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Analysis", exact: true });
  await expect(dialog).toContainText("Enable once for all existing and future experiments");
  await dialog.getByRole("button", { name: "Enable AI analysis", exact: true }).click();
  await expect(dialog.locator(".analysis-mode")).toHaveText("AI analysis");
  expect(fixture.saves).toBe(1); expect(starts).toBe(2);
  await dialog.getByRole("button", { name: "Close analysis" }).click();
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  await expect(dialog.locator(".analysis-mode")).toHaveText("AI analysis");
  expect(starts).toBe(2);
  await dialog.getByRole("button", { name: "Close analysis" }).click();
  await page.goto("/comparison?candidate=logistic_regression%2Flr1");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  await expect(dialog.locator(".analysis-mode")).toHaveText("AI analysis");
  await expect(dialog.getByRole("button", { name: "Enable AI analysis", exact: true })).toHaveCount(0);
  expect(fixture.saves).toBe(1); expect(starts).toBe(3);
  fixture.allowed = false; // Another window revoked the workspace permission.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(dialog.locator(".analysis-mode")).toHaveText("Recorded evidence");
  await expect(dialog.getByRole("button", { name: "Enable AI analysis", exact: true })).toBeVisible();
  expect(starts).toBe(3); // Focus recovery only verifies with GETs.
});
