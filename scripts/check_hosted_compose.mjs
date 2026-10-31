import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("..", import.meta.url));
const environment = resolve(root, process.argv[2] ?? ".env.hosted");
const result = spawnSync("docker", ["compose", "--env-file", environment, "-f", "compose.hosted.yaml", "config", "--format", "json"], {
  cwd: root, encoding: "utf8", timeout: 10000, env: { ...process.env, SIDEKICK_HOSTED_ENV_FILE: environment }
});
if (result.error || result.status !== 0) {
  console.error("Hosted Compose validation failed. Check Docker Compose and the selected environment file.");
  process.exit(1);
}
const config = JSON.parse(result.stdout);
const workspace = config.services.workspace;
assert.ok(!workspace.ports?.length, "Only the HTTPS proxy may publish a workspace port");
assert.equal(workspace.build.target, "hosted");
assert.equal(workspace.environment.SIDEKICK_MODE, "full");
assert.equal(workspace.environment.SIDEKICK_ARTIFACTS_DIR, "/workspace/artifacts");
assert.equal(workspace.environment.FORWARDED_ALLOW_IPS, "*");
assert.equal(workspace.read_only, true);
assert.equal(Number(workspace.mem_limit), 2 * 1024 ** 3);
assert.ok(workspace.volumes.some(volume => volume.type === "volume" && volume.target === "/workspace"));
assert.ok(workspace.cap_drop.includes("ALL"));
// Compose escapes literal dollars when it renders a reusable configuration.
const passwordHash = (workspace.environment.SIDEKICK_HOSTED_PASSWORD_HASH ?? "").replaceAll("$$", "$");
if (!/^v1\$pbkdf2_sha256\$\d+\$[a-f0-9]{32}\$[a-f0-9]{64}$/.test(passwordHash)) {
  throw new Error("Hosted password hash was missing or altered by environment interpolation");
}
assert.deepEqual(config.services.proxy.ports.map(port => Number(port.published)).sort((a, b) => a-b), [80, 443]);
console.log("Hosted Compose checked: private API, persistent volume, restricted runtime and HTTPS proxy. Credentials were not displayed.");
