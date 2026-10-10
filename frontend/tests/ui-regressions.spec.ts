import { expect, test } from "@playwright/test";
import { fixtureLibrary, runId } from "./library-fixtures";
import { mkdirSync } from "node:fs";

const screenshots = "../output/playwright/remediation";
mkdirSync(screenshots, { recursive: true });

for (const theme of ["light", "dark"]) for (const width of [1280, 390]) {
  test(`${theme} ${width}px library preserves long names, keyboard and compact layout`, async ({ page }) => {
    const fixture = await fixtureLibrary(page);
    const long = "Pump commissioning review with a deliberately long equipment-family name ".repeat(2);
    fixture.state.items[0]!.display_name = long;
    await page.setViewportSize({ width, height: width === 390 ? 844 : 720 });
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), theme);
    await page.goto("/experiments");
    await expect(page.getByRole("row", { name: long, exact: true })).toBeVisible();
    await expect(page.getByText("Ready to train", { exact: true })).toBeVisible();
    await expect(page.getByText("completed", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${screenshots}/library-${theme}-${width}.png` });
    if (width === 390) {
      await page.getByRole("link", { name: long, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/experiments/${runId}/comparison`));
    } else {
      const row = page.getByRole("row", { name: long, exact: true });
      await row.click(); await row.press("F2");
      await expect(page.getByRole("textbox", { name: "Display name", exact: true })).toBeFocused();
      await page.keyboard.press("Escape"); await expect(row).toBeFocused();
    }
  });
}

test("reduced motion renders final counts, static canvas and beam, and responds to preference changes", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "false");
  for (const counter of await page.locator("[data-rolling-number]").all()) {
    await expect(counter.locator('> span[aria-hidden="true"]').nth(1)).toHaveText((await counter.getAttribute("data-value"))!);
  }
  const pixels = await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL());
  await page.mouse.move(850, 340); await page.waitForTimeout(150);
  expect(await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL())).toBe(pixels);
  expect(await page.locator("[data-beam]").evaluate(beam => getComputedStyle(beam, "::before").display)).toBe("none");
  await expect.poll(() => page.locator("[data-overview-fill]").first().evaluate(fill => {
    const transform = getComputedStyle(fill).transform;
    return transform === "none" || new DOMMatrixReadOnly(transform).isIdentity;
  })).toBe(true);
  await page.screenshot({ path: `${screenshots}/overview-reduced-motion.png` });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "true");
  await page.mouse.move(900, 400); await page.waitForTimeout(100);
  const moving = await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL());
  await page.waitForTimeout(100);
  expect(await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL())).not.toBe(moving);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(canvas.locator("..")).toHaveAttribute("data-active", "false");
  const finalPixels = await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL());
  await page.mouse.move(550, 250); await page.waitForTimeout(150);
  expect(await canvas.evaluate(canvas => (canvas as HTMLCanvasElement).toDataURL())).toBe(finalPixels);
  await page.goto("/replay");
  const slider = page.getByRole("slider", { name: "Replay cycle", exact: true });
  await expect(slider).toBeVisible();
  await slider.focus(); await slider.press("Home");
  await expect(slider).toHaveAttribute("aria-valuenow", "0");
  await slider.press("ArrowRight");
  await expect(slider).toHaveAttribute("aria-valuenow", "1");
});

test("renamed archived result identifies the run with its original source and evidence scope", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  const label = "Pump fleet: commissioning baseline ".repeat(4);
  await page.route(`**/api/experiments/${runId}`, route => route.fulfill({ json: {
    experiment_id: runId, dataset_id: "fixture", name: "pump.csv", display_name: label, source: "upload",
    status: "completed", created_at: 100, config: {}, config_fingerprint: "fixture", data_hash: "fixture", source_digest: "fixture",
  } }));
  await page.route("**/api/*?*", async route => {
    const url = new URL(route.request().url());
    url.searchParams.delete("experiment_id"); url.searchParams.delete("experiment");
    const response = await route.fetch({ url: url.toString() });
    await route.fulfill({ response });
  });
  await page.goto(`/experiments/${runId}/comparison`);
  const source = page.locator("details.source-chip > summary");
  await expect(source).toHaveAccessibleName(new RegExp("Pump fleet: commissioning baseline"));
  await expect(source.locator("strong")).toHaveAttribute("title", label);
  await source.click();
  await expect(page.locator(".source-popover")).toContainText("Uploaded data");
  await expect(page.locator(".source-popover")).toContainText("Development results");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
