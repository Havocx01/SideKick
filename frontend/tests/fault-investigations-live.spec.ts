import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Paid: runs only with SIDEKICK_BROWSER_LIVE=1 and Nebius and Tavily keys in the server's environment: a Nemotron search within 2 calls and
// 10240 completion tokens, then one fault research action (one Tavily search and at most one Nemotron request).
const artifacts = process.env.SIDEKICK_BROWSER_ARTIFACTS!;
test.skip(process.env.SIDEKICK_BROWSER_LIVE !== "1", "Live browser test needs SIDEKICK_BROWSER_LIVE=1");

test.beforeAll(() => {
  execFileSync(process.env.SIDEKICK_TEST_PYTHON ?? "python", ["scripts/demo_investigation.py", "--root", `${artifacts}/investigations`, "--output", `${artifacts}/demo.json`],
    { cwd: "..", stdio: "ignore", env: { ...process.env, PYTHONPATH: "backend" } });
});

test("a consented Nemotron search runs from the browser within its allowance", async ({ page }) => {
  test.setTimeout(600_000);
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.goto("/investigations");
  await page.getByRole("button", { name: "AI settings", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Workspace AI", exact: true });
  await dialog.getByRole("button", { name: "Enable AI permission", exact: true }).click();
  await expect(dialog).toContainText("AI permission is enabled.");
  await page.keyboard.press("Escape");

  await page.getByRole("link", { name: /^Demo: find sensor faults/ }).first().click();
  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop()!;
  await page.getByRole("button", { name: /^Run more fault tests/ }).click();
  await page.getByLabel("Provider calls").fill("2");
  await page.getByLabel("Completion token ceiling").fill("10240");
  await page.getByRole("checkbox", { name: "Allow sending this information to Nebius for this run" }).check();
  await page.getByRole("button", { name: "Start Nemotron search" }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/investigations/${id}`)).json()).active, { timeout: 540_000, intervals: [2000] }).toBeNull();

  await page.reload();
  await page.getByRole("button", { name: /^Activity and proposed tests/ }).click();
  const calls = page.getByRole("table", { name: "Provider calls" });
  await expect(calls).toBeVisible();
  const view = await (await page.request.get(`/api/investigations/${id}`)).json();
  expect(view.controller.callsUsed).toBeGreaterThan(0);
  expect(view.controller.callsUsed).toBeLessThanOrEqual(2);
  expect(view.controller.reservedCompletionTokens).toBeLessThanOrEqual(10240);
  expect(view.events.at(-1).kind).toBe("finished:agent");
  if (view.controller.calls.some((call: { status: string }) => call.status === "accepted")) await expect(page.getByText("Chosen by Nemotron").first()).toBeVisible();
  await page.screenshot({ path: `../${artifacts}/live-investigation.png`, fullPage: true });

  const card = page.getByRole("article", { name: /^Measured failure: oil_particles:stuck\+vibration_rms:stuck/ });
  await card.getByRole("button", { name: "Research this fault" }).click();
  await card.getByRole("checkbox", { name: "Allow Tavily search and Nemotron research for this fault" }).check();
  await card.getByRole("button", { name: "Start fault research" }).click();
  await expect.poll(async () => (await (await page.request.get(`/api/investigations/${id}`)).json()).research?.[0]?.status, { timeout: 120_000, intervals: [2000] })
    .toMatch(/^(completed|failed)$/);
  const research = (await (await page.request.get(`/api/investigations/${id}`)).json()).research[0];
  expect(research.searchRequests).toBe(1);
  expect(research.modelRequests).toBeLessThanOrEqual(1);
  await page.reload();
  await expect(card).toContainText("Fault research");
  await expect(card).toContainText(research.status);
  await card.screenshot({ path: `../${artifacts}/live-research.png` });

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Public evidence" }).click();
  const evidence = JSON.parse(readFileSync(await (await download).path(), "utf-8"));
  expect(evidence.controller.callsUsed).toBe(view.controller.callsUsed);
  expect(JSON.stringify(evidence)).not.toContain("Demo: find sensor faults");

});
