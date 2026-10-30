import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// No mocked routes: these drive the real server, its registry and its background workers. No provider calls are made.
const artifacts = process.env.SIDEKICK_BROWSER_ARTIFACTS!;
test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  execFileSync(process.env.SIDEKICK_TEST_PYTHON ?? "python", ["scripts/demo_investigation.py", "--root", `${artifacts}/investigations`, "--output", `${artifacts}/demo.json`],
    { cwd: "..", stdio: "ignore", env: { ...process.env, PYTHONPATH: "backend" } });
});

async function saved(page: Page, id: string) {
  const response = await page.request.get(`/api/investigations/${id}`);
  expect(response.ok()).toBe(true);
  return response.json();
}

test("a real run starts once despite repeated clicks and a refresh", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.goto("/investigations");
  await page.getByLabel("Experiment budget").fill("4");
  await page.getByRole("button", { name: "Create investigation" }).click();
  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop()!;
  const run = page.getByRole("button", { name: "Run saved proposals" });
  await run.click();
  await page.reload();
  const more = page.getByRole("button", { name: /^Run (more|your first) fault tests/ });
  if (await more.getAttribute("aria-expanded") === "false") await more.click();
  if (await run.isVisible() && await run.isEnabled()) await run.click();
  await expect(page.getByText("All proposals run").first()).toBeVisible({ timeout: 60_000 });
  const view = await saved(page, id);
  expect(view.experimentsUsed).toBe(3);
  expect(view.state.attempts.length).toBe(3);
  expect(new Set(view.state.attempts.map((item: { scenario_id: string }) => item.scenario_id)).size).toBe(3);
});

test("a finished investigation replays, reduces, compares a remedy and exports through the browser", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.goto("/investigations");
  await page.getByRole("link", { name: /^Demo: find sensor faults/ }).first().click();
  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop()!;
  const before = await saved(page, id);
  const card = page.getByRole("article", { name: /Measured failure: oil_particles:stuck\+vibration_rms:stuck/ });
  await card.getByRole("button", { name: "Replay" }).click();
  await expect(card.getByRole("status")).toHaveText("Replay reproduced this result exactly.", { timeout: 60_000 });
  await card.getByRole("button", { name: "Reduce" }).click();
  await expect.poll(async () => (await saved(page, id)).reductions.length, { timeout: 60_000 }).toBe(before.reductions.length + 1);
  await expect.poll(async () => (await saved(page, id)).active, { timeout: 60_000 }).toBeNull();
  await page.reload();
  await page.getByLabel("Threshold").fill("0.6");
  await page.getByRole("button", { name: "Compare remedy" }).click();
  await expect.poll(async () => (await saved(page, id)).remedies.length, { timeout: 60_000 }).toBe(before.remedies.length + 1);
  await expect.poll(async () => (await saved(page, id)).active, { timeout: 60_000 }).toBeNull();
  await page.reload();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Public evidence" }).click();
  const evidence = JSON.parse(readFileSync(await (await download).path(), "utf-8"));
  expect(evidence.remedies.map((item: { threshold: number }) => item.threshold)).toEqual([0.5, 0.6]);
  expect(evidence.validations[0].status).toBe("assessed");
  expect(evidence.digest).toMatch(/^[0-9a-f]{64}$/);
  expect(JSON.stringify(evidence)).not.toContain("Demo: find sensor faults");
});
