import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("..", import.meta.url));
const result = spawnSync("docker", ["compose", "config", "--format", "json"], { cwd: root, encoding: "utf8" });
if (result.error || result.status !== 0) {
  // Rendered configuration may contain secrets. Never echo stdout or stderr.
  console.error("Compose configuration could not be rendered. Install Docker Compose and check your local configuration.");
  process.exit(1);
}
const config = JSON.parse(result.stdout);
for (const [name, port] of [["api", 8000], ["web", 5173]]) {
  const service = config.services[name];
  assert.ok(service, `Missing ${name} service`);
  assert.equal(service.ports.length, 1, `${name} must publish only its local development port`);
  assert.equal(service.ports[0].host_ip, "127.0.0.1", `${name} must bind host loopback`);
  assert.equal(service.ports[0].target, port);
  assert.equal(String(service.ports[0].published), String(port));
  assert.ok(JSON.stringify(service.command).includes("0.0.0.0"), `${name} must remain reachable inside its container`);
}
assert.equal(config.services.web.environment.SIDEKICK_API_URL, "http://api:8000");
console.log("Compose checked: API 127.0.0.1:8000, web 127.0.0.1:5173; container networking retained.");
