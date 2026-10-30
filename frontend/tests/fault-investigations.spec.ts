import { expect, test, type Page } from "@playwright/test";
import type { ContextInfo, Finding, InvestigationView } from "../src/api/types";

const LR = "logistic_regression/lr-probe";
const stuckPair = { components: [{ sensor: "vibration_rms", kind: "stuck", duration: "persistent", onset_before_failure: 60 },
  { sensor: "oil_particles", kind: "stuck", duration: "persistent", onset_before_failure: 60 }] };
const context: ContextInfo = { name: "synthetic", contextFingerprint: "a".repeat(64), profile: "synthetic-rotating-v1", sensors: ["vibration_rms", "oil_particles"],
  thresholds: { [LR]: 0.95 }, clean: { [LR]: { detection: 1, alarmBurden: 0, medianLead: 17, histories: 22 } } };
const criterion = { candidate: LR };
const failure: Finding = {
  status: "measured_failure", criterion, criterion_fingerprint: "c", proposal_id: "p1", attempt_id: "a1", scenario_id: "compound-v1-x",
  family: "oil_particles:stuck+vibration_rms:stuck", evidence_digest: "d".repeat(64), expected_histories: 22, evaluated_histories: 22, coverage: 1,
  clean_detection: 1, faulted_detection: 0.73, clean_burden: 0, faulted_burden: 0, reasons: [],
  assumptions: ["Bearing temperature, vibration and particle count share one condition-monitoring module. (prototype assumption)"],
  effects: [{ kind: "late_warnings", histories: ["SYN-001", "SYN-002"] }],
  support: [{ equipment_id: "SYN-001", clean: "detected", faulted: "late", clean_lead: 17, faulted_lead: null, clean_episodes: 1, faulted_episodes: 1 }]
};

function view(overrides: Partial<InvestigationView> = {}): InvestigationView {
  return {
    id: "inv-1", context: "synthetic", objective: "Find sensor faults that cost useful warnings.", createdAt: 1_760_000_000, active: null, stopReason: null,
    experimentsUsed: 0, maxExperiments: 16, discoveries: 0, discoveryFamilies: [], criterion, findings: [], controller: null, reductions: [], remedies: [],
    state: { id: "inv-1", context_fingerprint: "a".repeat(64), policy_fingerprint: "b".repeat(64), budget: { max_experiments: 16, max_failures: 3, max_attempts_per_scenario: 2, max_run_seconds: 600 },
      cancel_requested: false, stop_reason: null, slots_used: 0, failures: 0, proposals: [], attempts: [] },
    proposals: [{ id: "p1", sequence: 1, status: "pending", scenario: stuckPair, reason: "Freeze two monitoring channels.", hypothesis: null, rejection: null },
      { id: "p2", sequence: 2, status: "rejected", scenario: { components: [{ sensor: "rated_voltage", kind: "dropout", duration: "persistent", onset_before_failure: 40 }] },
        reason: "Constant channel", hypothesis: null, rejection: "ValueError: Scenario uses a sensor outside the allowed mapping" }],
    events: [{ sequence: 1, kind: "created", detail: "Context synthetic", at: 1_760_000_000 }],
    ...overrides
  } as InvestigationView;
}

const finished = () => view({ experimentsUsed: 1, discoveries: 1, discoveryFamilies: [failure.family!], stopReason: "completed", findings: [failure],
  events: [{ sequence: 1, kind: "created", detail: null, at: 1_760_000_000 }, { sequence: 2, kind: "started:run", detail: null, at: 1_760_000_010 },
    { sequence: 3, kind: "finished:run", detail: "completed", at: 1_760_000_020 }],
  proposals: view().proposals.map(item => item.id === "p1" ? { ...item, status: "completed" } : item) });

async function fixture(page: Page, initial: InvestigationView, contexts: ContextInfo[] = [context]) {
  const state = { current: initial, posts: [] as { path: string; body: Record<string, unknown> | null }[], gets: 0 };
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  await page.route("**/api/investigations**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST") {
      expect(request.headers()["x-sidekick-request"]).toBe("1");
      const body = request.postData() ? request.postDataJSON() : null;
      state.posts.push({ path, body });
      if (path === "/api/investigations") return route.fulfill({ json: initial });
      if (path.endsWith("/replay")) return route.fulfill({ json: { attempt: "a1", scenarioId: failure.scenario_id, matches: true, evidenceDigest: failure.evidence_digest } });
      if (path.endsWith("/cancel")) state.current = { ...state.current, state: { ...state.current.state, cancel_requested: true } };
      if (path.endsWith("/resume")) state.current = { ...state.current, state: { ...state.current.state, cancel_requested: false } };
      if (path.endsWith("/start")) state.current = { ...state.current, active: (body as { mode: string }).mode };
      return route.fulfill({ json: state.current });
    }
    if (path === "/api/investigations/contexts") return route.fulfill({ json: contexts });
    if (path === "/api/investigations") return route.fulfill({ json: [initial] });
    if (path.endsWith("/public-export")) return route.fulfill({ json: { version: 1, digest: "e".repeat(64) } });
    if (path.endsWith("/export")) return route.fulfill({ json: state.current });
    state.gets++;
    if (state.current.active && state.gets > 2) state.current = finished();
    return route.fulfill({ json: state.current });
  });
  return state;
}

test("an empty registry explains how to add a fitted context", async ({ page }) => {
  await fixture(page, view(), []);
  await page.goto("/investigations");
  await expect(page.getByRole("heading", { name: "No fitted context yet" })).toBeVisible();
  await expect(page.locator("pre")).toContainText("evaluate_fault_scenarios.py --profile synthetic-rotating-v1");
});

test("create shows clean performance and saves the criterion", async ({ page }) => {
  const state = await fixture(page, view());
  await page.goto("/investigations");
  await expect(page.getByRole("link", { name: "Investigations", exact: true })).toBeVisible();
  const clean = page.getByRole("table", { name: "Clean performance" });
  await expect(clean).toContainText("100%");
  await expect(page.getByText("fault profile synthetic-rotating-v1")).toBeVisible();
  await page.getByLabel("Experiment budget").fill("8");
  await page.getByRole("button", { name: "Create investigation" }).click();
  await expect(page).toHaveURL(/\/investigations\/inv-1$/);
  expect(state.posts[0]).toEqual({ path: "/api/investigations", body: { context: "synthetic", objective: "Find sensor faults that cost useful warnings.",
    maxExperiments: 8, seed: 3, criterion: { candidate: LR } } });
});

test("a run is started explicitly, polled to completion and its finding can be inspected", async ({ page }) => {
  const state = await fixture(page, view());
  await page.goto("/investigations/inv-1");
  await expect(page.getByText("Opening this page never starts work.")).toBeVisible();
  await expect(page.getByText("Not started")).toBeVisible();
  expect(state.posts).toEqual([]);
  await expect(page.getByRole("cell", { name: /outside the allowed mapping/ })).toBeVisible();
  await page.getByRole("button", { name: "Run saved proposals" }).click();
  await expect(page.getByRole("heading", { name: "Running" })).toBeVisible();
  const start = state.posts.find(item => item.path.endsWith("/start"))!;
  expect(start.body).toMatchObject({ mode: "run" });
  expect(String(start.body!.requestId)).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  await expect(page.getByText("All proposals run").first()).toBeVisible({ timeout: 10_000 });
  const card = page.getByRole("article", { name: /Measured failure/ });
  await expect(card).toContainText("100% → 73%");
  await expect(card).toContainText("22 / 22 histories");
  await card.getByText("1 histories changed").click();
  await expect(card.getByRole("cell", { name: "SYN-001" })).toBeVisible();
  await card.getByText("Profile assumptions").click();
  await expect(card).toContainText("(prototype assumption)");
  await card.getByRole("button", { name: "Replay" }).click();
  await expect(card.getByRole("status")).toHaveText("Replay reproduced this result exactly.");
  await card.getByRole("button", { name: "Reduce" }).click();
  await expect.poll(() => state.posts.find(item => item.path.endsWith("/reduce"))?.body).toMatchObject({ attempt: "a1", maxExperiments: 16 });
});

test("provider search needs explicit consent and states what is sent", async ({ page }) => {
  const state = await fixture(page, view());
  await page.goto("/investigations/inv-1");
  const preview = page.getByRole("group", { name: "Nemotron search" });
  await expect(preview).toContainText("Never sent: sensor names, raw readings, equipment IDs");
  const start = page.getByRole("button", { name: "Start Nemotron search" });
  await expect(start).toBeDisabled();
  await page.getByLabel("Provider calls").fill("2");
  const consent = page.getByRole("checkbox", { name: "Allow sending this information to Nebius for this run" });
  await consent.focus(); await page.keyboard.press("Space");
  await expect(consent).toBeChecked();
  await start.click();
  await expect.poll(() => state.posts.find(item => item.path.endsWith("/start"))?.body).toMatchObject({ mode: "agent", allowProvider: true, maxProviderCalls: 2 });
});

test("cancel, resume, failures and interruptions are shown distinctly", async ({ page }) => {
  const state = await fixture(page, view({ active: "agent" }));
  state.gets = -100;
  await page.goto("/investigations/inv-1");
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect.poll(() => state.posts.some(item => item.path.endsWith("/cancel"))).toBe(true);
  state.current = { ...state.current, active: null, stopReason: "cancelled" };
  await page.reload();
  await expect(page.getByRole("heading", { name: "Cancellation is saved" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run saved proposals" })).toBeDisabled();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByRole("button", { name: "Run saved proposals" })).toBeEnabled();

  state.current = view({ events: [{ sequence: 1, kind: "failed:agent", detail: "APIConnectionError: Connection error.", at: 1_760_000_000 }] });
  await page.reload();
  await expect(page.getByRole("heading", { name: "The last operation failed" })).toBeVisible();
  state.current = view({ events: [{ sequence: 1, kind: "interrupted", detail: "The server restarted during this operation.", at: 1_760_000_000 }] });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Interrupted" })).toBeVisible();
});

test("remedies need approval for retraining and evidence exports as JSON", async ({ page }) => {
  const state = await fixture(page, finished());
  await page.goto("/investigations/inv-1");
  await page.getByLabel("Threshold").fill("0.5");
  await page.getByRole("button", { name: "Compare remedy" }).click();
  await expect.poll(() => state.posts.find(item => item.path.endsWith("/remedies"))?.body).toMatchObject({ kind: "threshold", threshold: 0.5, approveTraining: false });
  await page.getByRole("combobox", { name: "Remedy" }).click();
  await page.getByRole("option", { name: "Augmented retraining" }).click();
  await expect(page.getByRole("button", { name: "Compare remedy" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "Approve development-only retraining" }).check();
  await expect(page.getByRole("button", { name: "Compare remedy" })).toBeEnabled();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence" }).click();
  expect((await download).suggestedFilename()).toBe("sidekick-investigation-inv-1.json");
  const publicDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Public evidence" }).click();
  expect((await publicDownload).suggestedFilename()).toBe("sidekick-investigation-inv-1-public.json");
});

for (const width of [390, 1280]) {
  test(`the workbench fits ${width}px without horizontal scrolling`, async ({ page }) => {
    await fixture(page, finished());
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/investigations/inv-1");
    await expect(page.getByRole("article", { name: /Measured failure/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test("each kind of outcome looks different and unscored cases say why", async ({ page }) => {
  const partial: Finding = { ...failure, status: "inconclusive", proposal_id: "p3", attempt_id: "a3", evaluated_histories: 10, coverage: 10 / 22,
    effects: [], support: [], reasons: ["Coverage 45% is below the 80% minimum"] };
  const inapplicable: Finding = { ...failure, status: "not_applicable", proposal_id: "p4", attempt_id: "a4", evaluated_histories: 0, coverage: 0,
    clean_detection: null, faulted_detection: null, effects: [], support: [], reasons: ["channel-1: history never reaches 100 cycles before failure"] };
  const broken: Finding = { ...failure, status: "execution_error", proposal_id: "p5", attempt_id: "a5", reasons: ["timed_out"] };
  const proposals = [...view().proposals, ...["p3", "p4", "p5"].map((id, index) => ({ id, sequence: index + 3, status: "completed", scenario: stuckPair, reason: "Probe.",
    hypothesis: { suspected: "Stuck pair hides wear.", supportIf: "Warnings are lost.", weakenIf: "Warnings hold.", basedOn: [] }, rejection: null }))];
  const controller = { callsUsed: 2, reservedCompletionTokens: 10240, reportedCompletionTokens: 700, calls: [
    { sequence: 1, status: "rejected", proposalId: null, error: "invalid_proposal", feedback: "No development history can apply this case (22 checked)", reservedCompletionTokens: 5120, usage: { completion_tokens: 300 }, elapsedSeconds: 3 },
    { sequence: 2, status: "accepted", proposalId: "p3", error: null, feedback: null, reservedCompletionTokens: 5120, usage: { completion_tokens: 400 }, elapsedSeconds: 2 }] };
  await fixture(page, view({ ...finished(), findings: [failure, partial, inapplicable, broken], proposals, controller, stopReason: "budget_exhausted" } as Partial<InvestigationView>));
  await page.goto("/investigations/inv-1");
  const measured = page.getByRole("article", { name: /^Measured failure/ });
  await expect(measured).toContainText("Supplied case");
  await expect(measured).not.toContainText("Partial coverage");
  const inconclusive = page.getByRole("article", { name: /^Inconclusive/ });
  await expect(inconclusive).toContainText("Partial coverage");
  await expect(inconclusive).toContainText("Chosen by Nemotron");
  await expect(inconclusive).toContainText("Why this was not scored as a finding:");
  const notApplicable = page.getByRole("article", { name: /^Not applicable/ });
  await expect(notApplicable).toContainText("history never reaches 100 cycles before failure");
  await expect(page.getByRole("article", { name: /^Execution error/ })).toContainText("timed_out");
  const calls = page.getByRole("table", { name: "Provider calls" });
  await expect(calls).toContainText("rejected: invalid proposal");
  await expect(calls).toContainText("Not run: No development history can apply this case (22 checked)");
  await expect(calls.getByRole("columnheader", { name: "Reserved ceiling" })).toBeVisible();
  await expect(calls).toContainText("5120");
  await expect(page.getByText("Calls used 2; reserved 10240 tokens; reported 700.")).toBeVisible();
  await expect(page.getByText("Reasons and hypotheses are unverified text; only measured results above are evidence.")).toBeVisible();
});
