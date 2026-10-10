import { expect, test } from "@playwright/test";
import type { AnalysisRecord } from "../src/api/types";

for (const scenario of [
  { action: "Investigate failure", title: "Analysis", working: "Analyzing evidence", theme: "light", width: 1440 },
  { action: "Prepare review brief", title: "Review brief", working: "Preparing review brief", theme: "dark", width: 390 },
]) {
  test(`${scenario.title} hides provisional output until completion`, async ({ page }, testInfo) => {
    await page.addInitScript(theme => localStorage.setItem("sidekick-theme", theme), scenario.theme);
    await page.setViewportSize({ width: scenario.width, height: 900 });
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    let completed: AnalysisRecord;
    let finished = false;
    let releaseStart!: () => void;
    const startGate = new Promise<void>(resolve => { releaseStart = resolve; });
    await page.route(/\/api\/assistant\/analyses(?:\?.*)?$/, async route => {
      completed = await (await route.fetch()).json();
      await startGate;
      await route.fulfill({ json: { ...completed, status: "running", stages: completed.stages.map((stage, index) => ({ ...stage, status: index === 0 ? "completed" : index === 1 ? "running" : "pending" })) } });
    });
    await page.route("**/api/assistant/analyses/*", async route => {
      if (route.request().method() !== "GET") return route.continue();
      await route.fulfill({ json: finished ? completed : { ...completed, status: "running", stages: completed.stages.map((stage, index) => ({ ...stage, status: index === 0 ? "completed" : index === 1 ? "running" : "pending" })) } });
    });
    await page.getByRole("button", { name: scenario.action, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: scenario.title, exact: true });
    const progress = dialog.getByRole("region", { name: "Analysis progress", exact: true });
    await expect(progress).toContainText(scenario.working);
    await expect(dialog.locator(".analysis-ai-setup, .analysis-rerun, .analysis-layout, .review-workspace, .analysis-audit")).toHaveCount(0);
    releaseStart();
    await expect(progress).toContainText("Investigate evidence");
    await expect(dialog.locator(".analysis-ai-setup, .analysis-rerun, .analysis-layout, .review-workspace, .analysis-audit")).toHaveCount(0);
    await expect(dialog.getByRole("link")).toHaveCount(0);
    const toggle = progress.getByRole("button", { name: scenario.working, exact: true });
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(progress.getByRole("list", { name: "Analysis steps" })).not.toBeVisible();
    await page.keyboard.press("Enter");
    await expect(progress.getByRole("list", { name: "Analysis steps" })).toBeVisible();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(progress.locator(".assistant-thinking-label")).toHaveCSS("animation-name", "none");
    expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`thinking-${scenario.theme}.png`), animations: "disabled" });
    finished = true;
    await expect(progress).toHaveCount(0);
    await expect(dialog.locator(".analysis-context")).toContainText("lr2");
    if (scenario.title === "Analysis") await expect(dialog.getByRole("region", { name: "Assessment" })).toContainText("39 fewer timely warnings");
    else await expect(dialog.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/^Engineer review draft/);
  });
}

test("answer reveal settles once, preserves layout and respects reduced motion", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  const answer = page.getByRole("region", { name: "Assessment", exact: true });
  await expect(answer).toHaveAttribute("aria-busy", "true");
  await expect(answer.locator(".assistant-stream-word").last()).toHaveCSS("opacity", "0");
  const initialHeight = (await answer.boundingBox())!.height;
  const nextCheck = page.getByRole("region", { name: "Next check", exact: true });
  await expect(nextCheck).not.toBeVisible();
  await expect(answer).toHaveAttribute("aria-busy", "false");
  expect(Math.abs((await answer.boundingBox())!.height - initialHeight)).toBeLessThan(1);
  await expect(answer.locator('.assistant-stream-word[data-revealed="false"]')).toHaveCount(0);
  await expect(nextCheck).toBeVisible();
  await answer.getByRole("button", { name: "Show evidence for finding 3" }).click();
  await expect(answer).toHaveAttribute("aria-busy", "false");
  await expect(answer.getByRole("region", { name: "Evidence for finding 3" })).toContainText("41");
  await page.screenshot({ path: testInfo.outputPath("streamed-answer-desktop.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  await expect(answer).toHaveAttribute("aria-busy", "false");
  await expect(answer.locator('.assistant-stream-word[data-revealed="false"]')).toHaveCount(0);
  await expect(answer.locator(".assistant-stream-word").first()).toHaveCSS("transition-duration", "0s");
  expect(await page.getByRole("dialog").evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("streamed-answer-mobile.png"), animations: "disabled" });
});

test("analysis explains evidence inline and reuses it in a review", async ({ page }) => {
  const mutations: string[] = [];
  page.on("request", request => { if (request.method() === "POST") mutations.push(new URL(request.url()).pathname); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
  const assessment = page.getByRole("region", { name: "Assessment", exact: true });
  await expect(assessment).toContainText("39 fewer timely warnings");
  const location = page.url();
  await assessment.getByRole("button", { name: "Show evidence for finding 3" }).click();
  const proof = assessment.getByRole("region", { name: "Evidence for finding 3", exact: true });
  await expect(proof).toContainText("Histories warned in time");
  await expect(proof).toContainText("41");
  await expect(proof).toContainText("sensor_8");
  expect(page.url()).toBe(location);
  await expect(page.getByRole("dialog").getByRole("link")).toHaveCount(1);
  await assessment.getByRole("button", { name: "Show evidence for finding 3" }).click();
  await expect(proof).toHaveCount(0);
  await page.getByRole("button", { name: "Add to review brief", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Review brief", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/39 fewer timely warnings/);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export brief", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.zip$/);
  expect(mutations.every(path => path.startsWith("/api/assistant/"))).toBeTruthy();
});

test("analysis and briefs reopen saved evidence without another start", async ({ page }) => {
  let starts = 0;
  page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === "/api/assistant/analyses") starts += 1; });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  const open = async (name: string, admitted = false) => {
    const response = page.waitForResponse(reply => reply.request().method() === (admitted ? "POST" : "GET") && (admitted ? new URL(reply.url()).pathname === "/api/assistant/analyses" : /\/api\/assistant\/analyses\/[^/]+$/.test(new URL(reply.url()).pathname)));
    await page.getByRole("button", { name, exact: true }).click();
    const record = await (await response).json() as AnalysisRecord;
    if (name === "Prepare review brief") await expect(page.getByRole("textbox", { name: "Edit before saving" })).toBeVisible();
    else await expect(page.getByRole("region", { name: "Assessment", exact: true })).toHaveAttribute("aria-busy", "false");
    return record;
  };
  const close = async () => { await page.getByRole("button", { name: "Close analysis", exact: true }).click(); };
  const first = await open("Investigate failure", true);
  await close();
  expect((await open("Investigate failure")).id).toBe(first.id);
  expect(starts).toBe(1);
  await close();
  expect((await open("Prepare review brief")).id).toBe(first.id);
  const editor = page.getByRole("textbox", { name: "Edit before saving" });
  await editor.fill("Engineer notes: inspect sensor 8 before a supervised trial.");
  await close();
  expect((await open("Prepare review brief")).id).toBe(first.id);
  await expect(editor).toHaveValue("Engineer notes: inspect sensor 8 before a supervised trial.");
  expect(starts).toBe(1);
  await page.reload();
  expect((await open("Prepare review brief", true)).id).toBe(first.id);
  await expect(editor).toHaveValue("Engineer notes: inspect sensor 8 before a supervised trial.");
  await editor.fill("");
  await close();
  await open("Prepare review brief");
  await expect(editor).toHaveValue("");
  await editor.fill("Final engineer notes.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeEnabled();
  await close();
  await open("Investigate failure");
  await page.getByRole("button", { name: "Add to review brief", exact: true }).click();
  await expect(editor).toHaveValue("Final engineer notes.");
  await close();
  await page.getByRole("button", { name: "Inspect Logistic regression \u00b7 lr1", exact: true }).click();
  expect((await open("Investigate failure", true)).id).not.toBe(first.id);
  await close();
  await page.getByRole("button", { name: "Inspect Logistic regression \u00b7 lr2", exact: true }).click();
  expect((await open("Investigate failure", true)).id).toBe(first.id);
  expect(starts).toBe(4);
  await expect(page.getByRole("button", { name: "Rerun with AI", exact: true })).toHaveCount(0);
});

test("starting with a review brief reuses that evidence for analysis", async ({ page }) => {
  let starts = 0;
  page.on("request", request => { if (request.method() === "POST" && new URL(request.url()).pathname === "/api/assistant/analyses") starts += 1; });
  await page.goto("/comparison?candidate=xgboost_augmented%2Faug3");
  const briefResponse = page.waitForResponse(reply => new URL(reply.url()).pathname === "/api/assistant/analyses" && reply.request().method() === "POST");
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  const brief = await (await briefResponse).json() as AnalysisRecord;
  await expect(page.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/^Engineer review draft/);
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  const analysisResponse = page.waitForResponse(reply => new URL(reply.url()).pathname === `/api/assistant/analyses/${brief.id}` && reply.request().method() === "GET");
  await page.getByRole("button", { name: "Analyze result", exact: true }).click();
  const analysis = await (await analysisResponse).json() as AnalysisRecord;
  expect(analysis.id).toBe(brief.id);
  expect(analysis.result?.assessment).toEqual(brief.result?.assessment);
  await expect(page.getByRole("region", { name: "Verdict", exact: true })).toContainText("64 / 64");
  await expect(page.getByRole("region", { name: "Assessment", exact: true })).toHaveAttribute("aria-busy", "false");
  expect(starts).toBe(1);
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
    await page.screenshot({ path: testInfo.outputPath(`investigation-${theme}-mobile.png`), animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Investigate failure", exact: true })).toBeFocused();
  });
}
