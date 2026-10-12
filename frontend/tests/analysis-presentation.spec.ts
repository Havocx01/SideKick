import { expect, test } from "@playwright/test";
import type { AnalysisRecord } from "../src/api/types";

for (const theme of ["light", "dark"]) for (const width of [390, 1280]) {
  test(`saved analysis and full-width brief at ${width}px in ${theme}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.addInitScript(theme => {
      localStorage.setItem("sidekick-theme", theme);
      sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true");
    }, theme);
    const seed = await page.request.post("/api/assistant/analyses", {
      headers: { "X-Sidekick-Request": "1" }, data: { task: "investigate", candidates: ["logistic_regression/lr2"] },
    });
    expect(seed.ok()).toBeTruthy();
    const source = await seed.json() as AnalysisRecord;
    const record = { ...source, updated_at: source.created_at + 68423,
      error: "Cloud consent was revoked. Showing recorded evidence.", output_currency: "historical" };
    await page.route("**/api/assistant/analyses?reuse=true", route => route.fulfill({ json: record }));
    await page.route(`**/api/assistant/analyses/${record.id}/review`, route => route.fulfill({ json: {
      ...record, context: { ...record.context, task: "brief" },
      result: { ...record.result!, brief_draft: "Engineer review draft\n\nRecorded evidence and proposed next checks remain readable across the entire editor width.\n\n".repeat(12) },
    } }));
    await page.goto("/comparison?candidate=logistic_regression%2Flr2");
    await page.getByRole("button", { name: "Investigate failure", exact: true }).click();
    const analysis = page.getByRole("dialog", { name: "Analysis", exact: true });
    await expect(analysis.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
    await expect(analysis.getByRole("button", { name: "Analyzed evidence", exact: true })).toBeVisible();
    await expect(analysis).not.toContainText("68423s");
    await expect(analysis.getByRole("alert")).toHaveCount(0);
    await expect(analysis.getByRole("button", { name: "Retry analysis", exact: true })).toHaveCount(0);
    await expect(analysis.getByText("Previously saved analysis", { exact: true })).toHaveCount(0);
    await expect(analysis).toContainText("Saved AI output was removed");
    await analysis.getByRole("button", { name: "Add to review brief", exact: true }).click();
    const brief = page.getByRole("dialog", { name: "Review brief", exact: true });
    const editor = brief.getByRole("textbox", { name: "Edit before saving" });
    await expect(editor).toHaveValue(/Recorded evidence/);
    const dimensions = await editor.evaluate(node => ({
      width: node.getBoundingClientRect().width,
      parentWidth: node.parentElement!.getBoundingClientRect().width,
      background: getComputedStyle(node).backgroundColor,
      boxSizing: getComputedStyle(node).boxSizing,
    }));
    expect(dimensions.width).toBeGreaterThan(dimensions.parentWidth * .95);
    expect(dimensions.width).toBeLessThanOrEqual(dimensions.parentWidth);
    expect(dimensions.boxSizing).toBe("border-box");
    expect(dimensions.background).not.toBe("rgba(0, 0, 0, 0)");
    expect(await brief.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBeTruthy();
    await editor.focus();
    await expect(editor).toBeFocused();
    await brief.screenshot({ path: testInfo.outputPath(`review-${theme}-${width}.png`), animations: "disabled" });
  });
}

test("revoked deep output has one notice and one permitted retry", async ({ page }) => {
  const response = await page.request.post("/api/assistant/analyses", {
    headers: { "X-Sidekick-Request": "1" }, data: { task: "investigate", candidates: ["logistic_regression/lr2"] },
  });
  expect(response.ok()).toBeTruthy();
  const seed = await response.json() as AnalysisRecord;
  await page.route("**/api/assistant/capabilities*", route => route.fulfill({ json: {
    tasks: ["investigate", "brief", "deep"], live_available: false, deep_available: true,
    unlocked: true, consent_required: true, consent_granted: true, mode: "full", note: "Offline fixture",
  } }));
  await page.route("**/api/assistant/consent/workspace", route => route.fulfill({ json: {
    experiment_id: "workspace", allowed: true, disclosure: "Offline fixture",
  } }));
  await page.route("**/api/assistant/analyses?reuse=true", route => route.fulfill({ json: {
    ...seed, context: { ...seed.context, task: "deep" },
    error: "Cloud consent was revoked. Recorded evidence and proven evidence-only drafts remain available.",
    result: { ...seed.result!, fallback_reason: "Showing recorded evidence; live analysis access is off." },
  } }));
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Deep investigation", exact: true }).click();
  await page.getByRole("dialog", { name: "Plan an investigation" }).getByRole("button", { name: "Start investigation", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Deep investigation", exact: true });
  await expect(dialog).toContainText("Saved AI output was removed");
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Retry analysis", exact: true })).toHaveCount(1);
});
