import { expect, test, type Page } from "@playwright/test";
import type { AnalysisRecord } from "../src/api/types";

async function fixture(page: Page) {
  await page.route("https://api.openai.com/**", route => route.abort());
  const response = await page.request.post("/api/assistant/analyses", { headers: { "X-Sidekick-Request": "1" }, data: { task: "investigate", candidates: ["logistic_regression/lr2"] } });
  expect(response.ok()).toBeTruthy();
  const record = await response.json() as AnalysisRecord;
  await page.route("**/api/assistant/capabilities*", route => route.fulfill({ json: { tasks: ["investigate", "compare", "warning", "brief", "data"], live_available: true, unlock_available: false, unlocked: true, consent_required: false, consent_granted: true, mode: "full", note: "Fixture only" } }));
  return record;
}

const open = (page: Page) => page.getByRole("button", { name: "Investigate failure", exact: true }).click();

test("brief conversion shares the save queue and cannot replace newer engineer text", async ({ page }) => {
  const source = await fixture(page);
  const record = { ...source, brief_text: "Older saved notes.", brief_saved_at: 100 };
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let conversions = 0, saves = 0;
  await page.route("**/api/assistant/analyses?reuse=true", route => route.fulfill({ json: record }));
  await page.route(`**/api/assistant/analyses/${record.id}/review`, async route => {
    conversions += 1;
    await gate;
    await route.fulfill({ json: { ...record, context: { ...record.context, task: "brief" } } });
  });
  await page.route(`**/api/assistant/analyses/${record.id}/brief`, route => {
    saves += 1;
    const body = route.request().postDataJSON() as { text: string; draft_only: boolean };
    return route.fulfill({ json: { ...record, context: { ...record.context, task: "brief" }, brief_text: body.text, brief_saved_at: body.draft_only ? null : 200 } });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  await expect.poll(() => conversions).toBe(1);
  const editor = page.getByRole("textbox", { name: "Edit before saving" });
  await editor.fill("Newer engineering notes stay visible.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  expect(saves).toBe(0);
  await expect(editor).toHaveValue("Newer engineering notes stay visible.");
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeEnabled();
  await expect(editor).toHaveValue("Newer engineering notes stay visible.");
  expect(conversions).toBe(1);
});

test("a transient failed read recovers the existing analysis without another start", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0;
  await page.route("**/api/assistant/analyses*", async route => {
    const request = route.request();
    if (request.method() === "POST") {
      starts += 1;
      await route.fulfill({ json: { ...record, status: starts === 1 ? "running" : "completed" } });
    } else await route.continue();
  });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => {
    reads += 1;
    return reads === 1 ? route.fulfill({ status: 503, json: { detail: "Temporary fixture outage" } }) : route.fulfill({ json: record });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(reads).toBe(2);
  await expect(page.getByRole("button", { name: "Rerun with AI", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await open(page);
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(reads).toBe(3);
});

test("bounded failures expose GET-only refresh and close/reopen keeps the saved ID", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0, cancels = 0, fail = true;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: { ...record, status: "running" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => { reads += 1; return fail ? route.fulfill({ status: 503, json: { detail: "Fixture outage" } }) : route.fulfill({ json: record }); });
  await page.route(`**/api/assistant/analyses/${record.id}/cancel`, route => { cancels += 1; return route.fulfill({ json: { ...record, status: "cancelled" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}/review`, route => route.fulfill({ json: { ...record, context: { ...record.context, task: "brief" }, result: { ...record.result, brief_draft: "Engineer review draft\nSaved fixture evidence" } } }));
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  const refresh = page.getByRole("button", { name: "Refresh status", exact: true });
  await expect(refresh).toBeVisible({ timeout: 20000 });
  expect(reads).toBe(5); expect(starts).toBe(1);
  await page.waitForTimeout(1000); expect(reads).toBe(5);
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  fail = false;
  await open(page);
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(cancels).toBe(0); expect(reads).toBe(6);
  await page.getByRole("button", { name: "Add to review brief", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/Saved fixture evidence/);
  expect(starts).toBe(1);
});

for (const denial of [403, 404]) test(`manual refresh reads the saved job and ${denial} stops polling`, async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0, failure: number | null = 503;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: starts === 1 ? { ...record, status: "running" } : { ...record, id: "explicit-new-analysis" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => { reads += 1; return failure ? route.fulfill({ status: failure, json: { detail: failure !== 503 ? "Analysis unavailable in this browser" : "Fixture outage" } }) : route.fulfill({ json: record }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByRole("button", { name: "Refresh status", exact: true })).toBeVisible({ timeout: 20000 });
  failure = denial;
  await page.getByRole("button", { name: "Refresh status", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Analysis unavailable in this browser");
  await expect(page.getByRole("button", { name: "Refresh status", exact: true })).toHaveCount(0);
  const stoppedAt = reads;
  await page.waitForTimeout(1700);
  expect(reads).toBe(stoppedAt); expect(starts).toBe(1);
  await page.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(2);
});

test("Refresh status completes the saved analysis using GET only", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0, fail = true;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: { ...record, status: "running" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => { reads += 1; return fail ? route.fulfill({ status: 503, json: { detail: "Fixture outage" } }) : route.fulfill({ json: record }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByRole("button", { name: "Refresh status", exact: true })).toBeVisible({ timeout: 20000 });
  fail = false;
  await page.getByRole("button", { name: "Refresh status", exact: true }).click();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(reads).toBe(6);
});

test("a late response from a replaced candidate cannot overwrite the current analysis", async ({ page }) => {
  const original = await fixture(page);
  const replacement: AnalysisRecord = { ...original, id: "replacement-context", context: { ...original.context, candidates: ["logistic_regression/lr1"] },
    result: { ...original.result!, assessment: [{ id: "replacement", text: "Replacement fixture assessment retained.", source_ids: [original.result!.sources[0]!.id] }] } };
  let starts = 0;
  let release: (() => void) | undefined;
  const held = new Promise<void>(resolve => { release = resolve; });
  let reading = false;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: starts === 1 ? { ...original, status: "running" } : replacement }); });
  await page.route(`**/api/assistant/analyses/${original.id}`, async route => { reading = true; await held; await route.fulfill({ json: original }); });
  await page.route(`**/api/assistant/analyses/${original.id}/cancel`, route => route.fulfill({ json: { ...original, status: "cancelled" } }));
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect.poll(() => reading).toBeTruthy();
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await page.getByRole("button", { name: "Inspect Logistic regression · lr1", exact: true }).click();
  await open(page);
  await expect(page.locator(".analysis-context")).toContainText("lr1");
  await expect(page.getByRole("region", { name: "Assessment", exact: true })).toContainText("Replacement fixture assessment retained.");
  release?.();
  await page.waitForTimeout(500);
  await expect(page.locator(".analysis-context")).toContainText("lr1");
  await expect(page.getByRole("region", { name: "Assessment", exact: true })).toContainText("Replacement fixture assessment retained.");
  expect(starts).toBe(2);
});

test("closing a delayed start and reopening as a brief retains one admitted job", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, cancels = 0, conversions = 0;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/assistant/analyses?reuse=true", async route => {
    starts += 1; await gate; await route.fulfill({ json: { ...record, status: "running" } });
  });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => route.fulfill({ json: { ...record, output_currency: "current" } }));
  await page.route(`**/api/assistant/analyses/${record.id}/cancel`, route => { cancels += 1; return route.fulfill({ json: { ...record, status: "cancelled" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}/review`, route => {
    conversions += 1;
    return route.fulfill({ json: { ...record, context: { ...record.context, task: "brief" }, result: { ...record.result!, brief_draft: "Engineer review draft\nOne admitted fixture job." } } });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page); await expect.poll(() => starts).toBe(1);
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  await expect(page.getByRole("region", { name: "Analysis progress", exact: true })).toContainText("Preparing review brief");
  expect(starts).toBe(1); expect(cancels).toBe(0);
  release();
  await expect(page.getByRole("textbox", { name: "Edit before saving" })).toHaveValue(/One admitted fixture job/);
  expect(starts).toBe(1); expect(cancels).toBe(0); expect(conversions).toBe(1);
});

test("a late admission is cancelled only after deliberate context replacement", async ({ page }) => {
  const record = await fixture(page);
  const replacement: AnalysisRecord = { ...record, id: "replacement-admission", context: { ...record.context, candidates: ["logistic_regression/lr1"] },
    result: { ...record.result!, assessment: [{ id: "replacement", text: "Replacement admission stays current.", source_ids: [record.result!.sources[0]!.id] }] } };
  let starts = 0, cancels = 0;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/assistant/analyses?reuse=true", async route => {
    starts += 1;
    if (starts === 1) { await gate; await route.fulfill({ json: { ...record, status: "running" } }); }
    else await route.fulfill({ json: replacement });
  });
  await page.route(`**/api/assistant/analyses/${record.id}/cancel`, route => { cancels += 1; return route.fulfill({ json: { ...record, status: "cancelled" } }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page); await expect.poll(() => starts).toBe(1);
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await page.getByRole("button", { name: "Inspect Logistic regression \u00b7 lr1", exact: true }).click();
  await open(page);
  await expect(page.getByRole("region", { name: "Assessment", exact: true })).toContainText("Replacement admission stays current.");
  release(); await expect.poll(() => cancels).toBe(1);
  await expect(page.getByRole("region", { name: "Assessment", exact: true })).toContainText("Replacement admission stays current.");
  expect(starts).toBe(2);
});

test("a completed reopen verifies access before revealing a historical answer", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: record }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, async route => { reads += 1; await gate; await route.fulfill({ json: { ...record, output_currency: "historical" } }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await open(page);
  await expect(page.getByRole("status").filter({ hasText: "Opening saved analysis" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Analysis progress", exact: true })).toHaveCount(0);
  release();
  await expect(page.getByText("Previously saved analysis", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(reads).toBe(1);
});

test("denied cached context hides its answer and does not offer a new analysis", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, denied = false;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: record }); });
  await page.route("**/api/assistant/capabilities*", route => denied
    ? route.fulfill({ status: 403, json: { detail: "This experiment is no longer accessible." } })
    : route.fulfill({ json: { tasks: ["investigate", "brief"], live_available: true, consent_required: false, mode: "full" } }));
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page); await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close analysis", exact: true }).click(); denied = true;
  await open(page);
  await expect(page.getByRole("alert")).toContainText("no longer accessible");
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry analysis", exact: true })).toHaveCount(0);
  expect(starts).toBe(1);
});

test("a fresh browser verifies a historical record returned by server reuse", async ({ page }) => {
  const record = await fixture(page);
  let starts = 0, reads = 0;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: { ...record, reused: true } }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => { reads += 1; return route.fulfill({ json: { ...record, output_currency: "historical" } }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByText("Previously saved analysis", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(1); expect(reads).toBe(1);
});

test("lost admission response requires explicit reuse recovery and never starts on reopen", async ({ page }) => {
  // This fixture is the job already admitted by the server before its response was lost.
  const record = await fixture(page);
  let starts = 0, reads = 0, cancels = 0;
  const reuseFlags: string[] = [];
  await page.route(/\/api\/assistant\/analyses(?:\?.*)?$/, route => {
    starts += 1; reuseFlags.push(new URL(route.request().url()).searchParams.get("reuse") ?? "false");
    return starts === 1 ? route.fulfill({ status: 503, json: { detail: "Admission response lost. No job ID returned." } })
      : route.fulfill({ json: { ...record, reused: true } });
  });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => { reads += 1; return route.fulfill({ json: { ...record, output_currency: "current" } }); });
  await page.route(`**/api/assistant/analyses/${record.id}/cancel`, route => { cancels += 1; return route.fulfill({ json: { ...record, status: "cancelled" } }); });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await open(page);
  await expect(page.getByRole("alert")).toContainText("Admission response lost");
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await open(page);
  await expect(page.getByRole("alert")).toContainText("Admission response lost");
  expect(starts).toBe(1); expect(reads).toBe(0); expect(cancels).toBe(0);
  await page.getByRole("button", { name: "Retry analysis", exact: true }).click();
  await expect(page.getByRole("region", { name: "Finding", exact: true })).toBeVisible();
  expect(starts).toBe(2); expect(reuseFlags).toEqual(["true", "true"]); expect(reads).toBe(1); expect(cancels).toBe(0);
});

test("typing during a delayed explicit save keeps the newer draft and export disabled", async ({ page }) => {
  const source = await fixture(page);
  const record = { ...source, context: { ...source.context, task: "brief" }, result: { ...source.result!, brief_draft: "Engineer review draft\nOriginal fixture text." } };
  let releaseSave!: () => void, releaseAutosave!: () => void;
  const saveGate = new Promise<void>(resolve => { releaseSave = resolve; });
  const autosaveGate = new Promise<void>(resolve => { releaseAutosave = resolve; });
  let explicit = 0, autosaves = 0;
  await page.route("**/api/assistant/analyses?reuse=true", route => route.fulfill({ json: record }));
  await page.route(`**/api/assistant/analyses/${record.id}/brief`, async route => {
    const body = route.request().postDataJSON() as { text: string; draft_only: boolean };
    if (body.draft_only && body.text === "Newer typing stays visible.") { autosaves += 1; await autosaveGate; }
    else if (!body.draft_only) { explicit += 1; if (explicit === 1) await saveGate; }
    await route.fulfill({ json: { ...record, brief_text: body.text, brief_saved_at: body.draft_only ? null : 100, updated_at: 100 } });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Edit before saving" });
  await editor.fill("Older explicit draft.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect.poll(() => explicit).toBe(1);
  await editor.fill("Newer typing stays visible.");
  releaseSave();
  await expect.poll(() => autosaves).toBe(1);
  await expect(editor).toHaveValue("Newer typing stays visible.");
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Save draft", exact: true })).toBeEnabled();
  releaseAutosave();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeEnabled();
  await expect(editor).toHaveValue("Newer typing stays visible.");
  expect(explicit).toBe(2);
});

test("a failed draft save survives close and access revalidation", async ({ page }) => {
  const source = await fixture(page);
  const record = { ...source, context: { ...source.context, task: "brief" }, result: { ...source.result!, brief_draft: "Engineer review draft\nPreviously stored text." } };
  let fail = true, writes = 0, starts = 0;
  await page.route("**/api/assistant/analyses?reuse=true", route => { starts += 1; return route.fulfill({ json: record }); });
  await page.route(`**/api/assistant/analyses/${record.id}`, route => route.fulfill({ json: { ...record, output_currency: "current" } }));
  await page.route(`**/api/assistant/analyses/${record.id}/brief`, route => {
    writes += 1;
    const body = route.request().postDataJSON() as { text: string; draft_only: boolean };
    return fail ? route.fulfill({ status: 503, json: { detail: "Draft fixture outage" } })
      : route.fulfill({ json: { ...record, brief_text: body.text, brief_saved_at: body.draft_only ? null : 100 } });
  });
  await page.goto("/comparison?candidate=logistic_regression%2Flr2");
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  const editor = page.getByRole("textbox", { name: "Edit before saving" });
  await editor.fill("Keep my unsaved engineer notes.");
  await expect(page.getByRole("alert")).toContainText("Draft fixture outage");
  await page.getByRole("button", { name: "Close analysis", exact: true }).click();
  await page.getByRole("button", { name: "Prepare review brief", exact: true }).click();
  await expect(editor).toHaveValue("Keep my unsaved engineer notes.");
  await expect(page.getByRole("alert")).toContainText("Draft fixture outage");
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeDisabled();
  fail = false;
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("button", { name: "Export brief", exact: true })).toBeEnabled();
  expect(starts).toBe(1); expect(writes).toBe(2);
});
