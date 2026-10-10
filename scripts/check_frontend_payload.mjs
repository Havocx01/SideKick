// Production static entry dependencies. --loaded also measures actual cold-route
// resource URLs captured by the browser (including eagerly requested lazy chunks).
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

const args = process.argv.slice(2);
const dist = resolve(args[0] || "frontend/dist");
const manifest = JSON.parse(readFileSync(resolve(dist, ".vite/manifest.json"), "utf8"));
const seen = new Set();
function visit(key) {
  if (seen.has(key)) return;
  seen.add(key);
  for (const child of manifest[key]?.imports || []) visit(child);
}
for (const [key, entry] of Object.entries(manifest)) if (entry.isEntry) visit(key);
const entryFiles = [...seen].map(key => manifest[key].file).filter(file => file.endsWith(".js"));
function measure(files) {
  const assets = [...new Set(files)].sort().map(file => ({
    file, raw: statSync(resolve(dist, file)).size,
    gzip: gzipSync(readFileSync(resolve(dist, file))).byteLength,
  }));
  return { assets, raw: assets.reduce((sum, asset) => sum + asset.raw, 0), gzip: assets.reduce((sum, asset) => sum + asset.gzip, 0) };
}
const loadedAt = args.indexOf("--loaded");
const report = { staticEntry: measure(entryFiles) };
if (loadedAt >= 0) {
  const loaded = JSON.parse(readFileSync(args[loadedAt + 1], "utf8"));
  const files = loaded.map(url => new URL(url, "http://localhost").pathname.replace(/^\//, "")).filter(file => file.endsWith(".js"));
  report.coldRoute = measure(files);
}
console.log(JSON.stringify(report, null, 2));
