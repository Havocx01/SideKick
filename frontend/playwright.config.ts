import { defineConfig } from "@playwright/test";

// Workers re-read this file, so the folder is fixed once in the environment they inherit.
process.env.SIDEKICK_BROWSER_ARTIFACTS ??= `output/browser-tests/${Date.now()}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8136", viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" },
  webServer: {
    command: `"${process.env.SIDEKICK_TEST_PYTHON ?? "python"}" -m uvicorn app.main:app --host 127.0.0.1 --port 8136`,
    url: "http://127.0.0.1:8136/api/health",
    cwd: "..",
    timeout: 30_000,
    env: { PYTHONPATH: "backend", SIDEKICK_MODE: "full", SIDEKICK_MLFLOW: "0", SIDEKICK_ASSISTANT_LIVE_ENABLED: "0", SIDEKICK_ARTIFACTS_DIR: process.env.SIDEKICK_BROWSER_ARTIFACTS },
  },
});
