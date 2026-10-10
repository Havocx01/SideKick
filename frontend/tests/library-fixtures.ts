import type { Page, Locator } from "@playwright/test";
import type { LibraryItem, LibrarySnapshot } from "../src/api/types";

export const folderId = "10000000-0000-4000-8000-000000000001";
export const uploadId = "20000000-0000-4000-8000-000000000001";
export const runId = "30000000-0000-4000-8000-000000000001";
export const runningId = "30000000-0000-4000-8000-000000000002";

export async function fixtureLibrary(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem("sidekick.walkthrough.intro.dismissed", "true"));
  const today = Date.now() / 1000;
  const item = (kind: "run" | "upload", id: string, name: string, status: string, date: number | null, folder: string | null = null): LibraryItem => ({
    kind, id, dataset_id: uploadId, display_name: name, original_name: `${name}.csv`, source: "upload",
    folder_id: folder, archived: false, created_at: date, status, run_count: 2, row_count: kind === "upload" ? 1234 : null,
  });
  const state: LibrarySnapshot = { folders: [{ id: folderId, name: "Pumps" }], items: [
    item("run", runId, "Alpha result", "completed", today - 10),
    item("upload", uploadId, "Beta upload", "ready_to_train", today - 30),
    item("run", runningId, "Gamma running", "running", today - 86400),
    item("upload", "20000000-0000-4000-8000-000000000002", "Delta unfinished", "needs_mapping", null, folderId),
  ] };
  const calls: { path: string; body: Record<string, unknown> }[] = [];
  let failNext = "";
  let libraryReads = 0;
  let uploads = 0;
  let uploadFailure = false;
  const dataset = { dataset_id: uploadId, source: "upload", name: "test.csv", columns: ["equipment_id", "cycle", "sensor", "failure_cycle"], preview: [{ equipment_id: "P1", cycle: 1, sensor: 0.5, failure_cycle: 2 }], row_count: 2, confirmed: false };
  await page.route("**/api/library**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET") { libraryReads++; await route.fulfill({ json: structuredClone(state) }); return; }
    const body = request.postDataJSON() ?? {};
    calls.push({ path, body });
    if (failNext) { const detail = failNext; failNext = ""; await route.fulfill({ status: 503, json: { detail } }); return; }
    if (path === "/api/library/folders" || path.endsWith("/rename")) {
      const name = String(body.name ?? "").trim();
      const existingId = path.endsWith("/rename") ? path.split("/").at(-2) : undefined;
      if (!name || name.length > 80 || state.folders.some(folder => folder.id !== existingId && folder.name.toLowerCase() === name.toLowerCase())) {
        await route.fulfill({ status: 409, json: { detail: "A folder with this name already exists. Choose another name." } }); return;
      }
      const folder = existingId ? state.folders.find(folder => folder.id === existingId)! : { id: "10000000-0000-4000-8000-000000000002", name };
      folder.name = name;
      if (!existingId) state.folders.push(folder);
      await route.fulfill({ status: existingId ? 200 : 201, json: folder }); return;
    }
    if (path.endsWith("/remove")) {
      const id = path.split("/").at(-2);
      state.folders = state.folders.filter(folder => folder.id !== id);
      for (const item of state.items) if (item.folder_id === id) item.folder_id = null;
    } else {
      const targets = state.items.filter(item => body.items.some((ref: { kind: string; id: string }) => ref.kind === item.kind && ref.id === item.id));
      if (body.action === "archive" && targets.some(item => ["queued", "running", "cancelling"].includes(item.status))) {
        await route.fulfill({ status: 409, json: { detail: "Active runs must finish before archiving." } }); return;
      }
      if (body.action === "move" && body.folder_id && !state.folders.some(folder => folder.id === body.folder_id)) {
        await route.fulfill({ status: 404, json: { detail: "This folder is unavailable. Choose another folder or Unfiled." } }); return;
      }
      for (const item of targets) {
        if (body.action === "rename") item.display_name = body.display_name;
        if (body.action === "move") item.folder_id = body.folder_id ?? null;
        if (body.action === "archive") item.archived = true;
        if (body.action === "restore") item.archived = false;
      }
    }
    await route.fulfill({ json: { ok: true } });
  });
  await page.route("**/api/datasets/upload", async route => {
    uploads++;
    calls.push({ path: "/api/datasets/upload", body: { folder: route.request().headers()["x-folder-id"] ?? null } });
    await route.fulfill(uploadFailure ? { status: 503, json: { detail: "Upload unavailable. Try again." } } : { json: dataset });
  });
  await page.route("**/api/datasets/*", route => route.request().method() === "GET"
    ? route.fulfill({ json: dataset }) : route.fallback());
  await page.route("**/api/experiments", async route => {
    if (route.request().method() !== "GET") throw new Error("Fixture browser journey must not start training");
    await route.fulfill({ json: [] });
  });
  return { state, calls, fail: (text: string) => { failNext = text; }, failUpload: (value: boolean) => { uploadFailure = value; }, reads: () => libraryReads, uploads: () => uploads };
}

export async function dragRow(page: Page, row: Locator, target: Locator) {
  const transfer = await page.evaluateHandle(() => new DataTransfer());
  await row.dispatchEvent("dragstart", { dataTransfer: transfer });
  await target.dispatchEvent("dragover", { dataTransfer: transfer });
  await target.dispatchEvent("drop", { dataTransfer: transfer });
  // A completed move/archive can remove the source row. Finish the native
  // gesture on the window listener without waiting for that old locator.
  await page.evaluate(transfer => window.dispatchEvent(new DragEvent("dragend", { dataTransfer: transfer })), transfer);
  await transfer.dispose();
}

export async function dropFiles(page: Page, target: Locator, names: string[]) {
  const transfer = await page.evaluateHandle(files => {
    const transfer = new DataTransfer();
    for (const name of files) transfer.items.add(new File(["equipment_id,cycle,sensor,failure_cycle\nP1,1,0.5,2\nP1,2,0.7,2\n"], name, { type: "text/csv" }));
    return transfer;
  }, names);
  await target.dispatchEvent("dragenter", { dataTransfer: transfer });
  await target.dispatchEvent("drop", { dataTransfer: transfer });
  await transfer.dispose();
}
