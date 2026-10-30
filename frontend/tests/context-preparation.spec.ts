import { expect, test } from "@playwright/test";
import type { ContextInfo } from "../src/api/types";

test("preparing another setup keeps the investigation draft and selected model", async ({ page }) => {
  const candidate = "logistic_regression/lr-probe";
  const context: ContextInfo = { name: "synthetic-original", contextFingerprint: "a".repeat(64), profile: "synthetic-rotating-v1", sensors: ["vibration_rms"],
    thresholds: { [candidate]: 0.5 }, clean: { [candidate]: { detection: 1, alarmBurden: 0, medianLead: 17, histories: 22 } } };
  let prepared = false;
  await page.route("**/api/investigations**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/investigations/contexts/preparation") {
      if (route.request().method() === "POST") prepared = true;
      const job = prepared ? { id: "prepared", status: "completed", stage: "ready", context: "synthetic-new", error: null, createdAt: 1 } : null;
      return route.fulfill({ json: route.request().method() === "POST" ? job : { job, outdated: 0 } });
    }
    if (path === "/api/investigations/contexts") return route.fulfill({ json: prepared ? [{ ...context, name: "synthetic-new" }, context] : [context] });
    return route.fulfill({ json: [] });
  });
  await page.goto("/investigations");
  await page.getByLabel("Concern").fill("Keep my unfinished investigation.");
  await page.getByLabel("Experiment budget").fill("7");
  const refreshed = page.waitForResponse(response => response.url().endsWith("/api/investigations/contexts"));
  await page.getByRole("button", { name: "Prepare another model setup", exact: false }).click();
  await page.getByRole("button", { name: "Prepare another sample", exact: true }).click();
  await refreshed;
  await expect(page.getByText("Sample models ready", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Model setup", exact: true })).toContainText("Rotating machine sample (iginal)");
  await expect(page.getByLabel("Concern")).toHaveValue("Keep my unfinished investigation.");
  await expect(page.getByLabel("Experiment budget")).toHaveValue("7");
});

test("sample models can be prepared in the app, reopened and used for a real investigation", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", request => { if (request.method() === "POST") posts.push(new URL(request.url()).pathname); });
  await page.goto("/investigations");
  const another = page.getByRole("button", { name: "Prepare another model setup", exact: false });
  if (await another.isVisible()) await another.click();
  const prepare = page.getByRole("button", { name: /^(Prepare sample models|Prepare another sample|Try preparation again)$/ });
  await expect(prepare).toBeVisible();
  expect(posts).toEqual([]);
  const started = page.waitForResponse(response => response.url().endsWith("/api/investigations/contexts/preparation") && response.request().method() === "POST");
  await prepare.click();
  const response = await started;
  expect(response.status()).toBe(202);
  const job = await response.json();
  await page.reload();
  await expect.poll(async () => {
    const result = await page.request.get(`/api/investigations/contexts/preparation/${job.id}`);
    return (await result.json()).status;
  }, { timeout: 60_000 }).toBe("completed");
  await expect(page.getByRole("heading", { name: "New investigation", exact: true })).toBeVisible();
  await expect(page.getByLabel("Performance before sensor faults")).toContainText("22");
  await expect(page.getByRole("combobox", { name: "Model under test", exact: true })).toContainText("Logistic regression");
  await page.getByLabel("Concern").fill("Check whether missing sensor readings cost useful warnings.");
  await page.getByLabel("Experiment budget").fill("4");
  await page.getByRole("button", { name: "Create investigation", exact: true }).click();
  await expect(page).toHaveURL(/\/investigations\/[0-9a-f-]{36}$/);
  await page.getByRole("button", { name: "Run saved proposals", exact: true }).click();
  await expect(page.getByText("All proposals run").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("article").first()).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Findings", exact: true })).toBeVisible();
  expect(posts.filter(path => path === "/api/investigations/contexts/preparation")).toHaveLength(1);
  expect(posts.filter(path => path.endsWith("/research"))).toHaveLength(0);
});

test("preparation explains stale setups, retains failures and permits an explicit retry", async ({ page }) => {
  let job: { id: string; status: string; stage: string; error: string | null; context: null; createdAt: number } | null = null;
  let starts = 0;
  await page.route("**/api/investigations**", route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/investigations/contexts/preparation") {
      if (request.method() === "POST") {
        starts++;
        job = { id: `prepare-${starts}`, status: "failed", stage: "training", context: null, error: "Preparation stopped. Try again.", createdAt: starts };
        return route.fulfill({ status: 202, json: job });
      }
      return route.fulfill({ json: { job, outdated: 2 } });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto("/investigations");
  await expect(page.getByRole("heading", { name: "Older model setups need refreshing" })).toBeVisible();
  await page.getByRole("button", { name: "Prepare sample models", exact: true }).click();
  await expect(page.getByText("Preparation stopped. Try again.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Preparation stopped. Try again.", { exact: true })).toBeVisible();
  expect(starts).toBe(1);
  await page.getByRole("button", { name: "Try preparation again", exact: true }).click();
  await expect.poll(() => starts).toBe(2);
  await expect(page.getByRole("heading", { name: "No investigations yet" })).toBeVisible();
});
