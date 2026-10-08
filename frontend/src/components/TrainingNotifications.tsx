import { useEffect } from "react";
import { toast } from "@/components/ui/toast";
import { experiments } from "../api/client";
import type { ExperimentRecord, JobStatus } from "../api/types";

const storageKey = "sidekick.training-notifications.v1";
const statuses = new Map<string, JobStatus>();
let restored = false;
const active = (status?: string) => status != null && ["queued", "running", "cancelling"].includes(status);

function restore() {
  if (restored) return;
  restored = true;
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(storageKey) ?? "[]");
    if (Array.isArray(saved)) for (const entry of saved) {
      if (Array.isArray(entry) && typeof entry[0] === "string" && ["queued", "running", "cancelling", "completed", "failed", "cancelled", "timed_out", "interrupted"].includes(entry[1])) statuses.set(entry[0], entry[1]);
    }
  } catch { /* Notifications still work when browser storage is unavailable. */ }
}

function persist() {
  const entries = [...statuses];
  const saved = entries.filter(([, status]) => active(status)).concat(entries.filter(([, status]) => !active(status)).slice(-200));
  try { sessionStorage.setItem(storageKey, JSON.stringify(saved)); } catch { /* Keep deduplication in memory. */ }
}

function updateTraining(record: ExperimentRecord, justStarted = false) {
  if (record.job_kind && record.job_kind !== "development") return false;
  const previous = statuses.get(record.experiment_id);
  if (previous === record.status) return false;
  statuses.set(record.experiment_id, record.status);
  if (record.status === "completed" && previous !== "completed" && (justStarted || active(previous))) {
    toast.add({ id: `training-${record.experiment_id}`, type: "success", title: "Training complete", description: `${record.name} · Results are ready.`, data: { href: `/experiments/${record.experiment_id}/comparison` } });
  }
  return true;
}

export function observeTraining(record: ExperimentRecord, justStarted = false) {
  restore();
  if (updateTraining(record, justStarted)) persist();
}

export function TrainingNotifications({ enabled }: { enabled: boolean }) {
  useEffect(() => {
    if (!enabled) return;
    restore();
    let alive = true;
    let pending = false;
    async function update() {
      if (pending) return;
      pending = true;
      try {
        const records = await experiments.list();
        if (alive) {
          let changed = false;
          for (const record of records) changed = updateTraining(record) || changed;
          if (changed) persist();
        }
      } catch { /* Experiment views handle errors; retry notification checks quietly. */ }
      finally { pending = false; }
    }
    void update();
    const timer = window.setInterval(update, 3000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [enabled]);
  return null;
}
