import { expect, test, type Page } from "@playwright/test";

async function hosted(page: Page) {
  const state = { authenticated: false, loginFails: false, logoutFails: false, expired: false, privateReads: [] as string[] };
  await page.context().route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const session = () => ({ required: true, authenticated: state.authenticated, owner: state.authenticated ? "adam" : null,
      budgets: state.authenticated ? { calls: 0, completionTokens: 0, searches: 0, mutations: 200 } : null });
    if (path === "/api/health") return route.fulfill({ json: { status: "ok", requires_sign_in: true, mode: "full", can_train: true, can_upload: true, can_review_pilot: true } });
    if (path === "/api/session") return route.fulfill({ json: session() });
    if (path === "/api/session/login") {
      expect(route.request().postDataJSON()).toEqual({ username: "adam", password: "example-password" });
      expect(route.request().headers()["x-sidekick-request"]).toBe("1");
      if (state.loginFails) return route.fulfill({ status: 401, json: { detail: "Username or password is incorrect." } });
      state.authenticated = true;
      return route.fulfill({ json: session() });
    }
    if (path === "/api/session/logout") {
      if (state.logoutFails) return route.fulfill({ status: 503, json: { detail: "Sign out failed. Try again." } });
      state.authenticated = false;
      return route.fulfill({ json: session() });
    }
    state.privateReads.push(path);
    if (state.expired) return route.fulfill({ status: 401, json: { detail: "Sign in to your private workspace." } });
    if (path === "/api/investigations/contexts/preparation") return route.fulfill({ json: { job: null, outdated: 0 } });
    if (["/api/investigations", "/api/investigations/contexts", "/api/experiments"].includes(path)) return route.fulfill({ json: [] });
    return route.fallback();
  });
  return state;
}

async function signIn(page: Page) {
  await page.getByLabel("Username", { exact: true }).fill("adam");
  await page.getByLabel("Password", { exact: true }).fill("example-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("private routes wait for sign-in and preserve the requested page", async ({ page }) => {
  const state = await hosted(page);
  await page.goto("/investigations");
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  expect(state.privateReads).toEqual([]);
  await signIn(page);
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/investigations$/);
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]).includes("example-password"))).toBe(false);
});

test("a rejected login clears the password and never mounts private data", async ({ page }) => {
  const state = await hosted(page);
  state.loginFails = true;
  await page.goto("/investigations");
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText("Username or password is incorrect");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  expect(state.privateReads).toEqual([]);
  state.loginFails = false;
  await signIn(page);
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
});

test("expired sessions hide the workspace without replaying the failed action", async ({ page }) => {
  const state = await hosted(page);
  state.authenticated = true;
  await page.goto("/investigations");
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  state.expired = true;
  state.authenticated = false;
  await page.getByRole("link", { name: "Experiments", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toHaveCount(0);
  await expect(page.getByText("Your session ended. Sign in again to continue.")).toBeVisible();
});

test("logout is confirmed by the server and clears another open tab", async ({ page, context }) => {
  const state = await hosted(page);
  state.authenticated = true;
  await page.goto("/investigations");
  const other = await context.newPage();
  await other.goto("/investigations");
  await expect(other.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  state.logoutFails = true;
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Sign out failed");
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  state.logoutFails = false;
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await expect(other.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
});

test("delayed 401 replies from an old session cannot clear a new login", async ({ page, context }) => {
  const state = await hosted(page);
  state.authenticated = true;
  let releaseFirst!: () => void;
  let releaseSecond!: () => void;
  const firstGate = new Promise<void>(resolve => { releaseFirst = resolve; });
  const secondGate = new Promise<void>(resolve => { releaseSecond = resolve; });
  let first = 0;
  let second = 0;
  await context.route("**/api/investigations/contexts", async route => {
    if (++first > 1) return route.fallback();
    await firstGate;
    return route.fulfill({ status: 401, json: { detail: "Old session expired" } });
  });
  await context.route("**/api/investigations", async route => {
    if (++second > 1) return route.fallback();
    await secondGate;
    return route.fulfill({ status: 401, json: { detail: "Old session expired" } });
  });
  await page.goto("/investigations");
  await expect.poll(() => first + second).toBe(2);
  state.authenticated = false;
  releaseFirst();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await signIn(page);
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  const oldResponse = page.waitForResponse(response => response.url().endsWith("/api/investigations") && response.status() === 401);
  releaseSecond();
  await oldResponse;
  await expect(page.getByRole("heading", { name: "Fault investigations", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toHaveCount(0);
});

for (const theme of ["light", "dark"]) {
  test(`private sign-in and toolbar fit mobile in ${theme}`, async ({ page }) => {
    const state = await hosted(page);
    await page.addInitScript(theme => document.documentElement.setAttribute("data-theme", theme), theme);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/investigations");
    await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await signIn(page);
    await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
    expect(state.authenticated).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
