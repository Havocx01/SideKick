import { useSyncExternalStore } from "react";

const key = "sidekick-motion";
const event = "sidekick-motion-change";
let sessionPreference: string | null = null;

export function readMotionPreference() {
  let preference = sessionPreference;
  try { preference = localStorage.getItem(key); } catch { /* Use the session choice when storage is unavailable. */ }
  return preference === "reduced";
}

export function setMotionPreference(reduced: boolean) {
  sessionPreference = reduced ? "reduced" : "full";
  try { localStorage.setItem(key, sessionPreference); } catch { /* The current tab can still change motion. */ }
  window.dispatchEvent(new Event(event));
}

export const subscribeMotionPreference = (changed: () => void) => {
  const storageChanged = (update: StorageEvent) => { if (update.key === key || update.key === null) changed(); };
  window.addEventListener(event, changed);
  window.addEventListener("storage", storageChanged);
  return () => {
    window.removeEventListener(event, changed);
    window.removeEventListener("storage", storageChanged);
  };
};

// Animate by default; an explicit app-only off choice survives refresh.
export function useMotionPreference() {
  return useSyncExternalStore(subscribeMotionPreference, readMotionPreference, () => false);
}
