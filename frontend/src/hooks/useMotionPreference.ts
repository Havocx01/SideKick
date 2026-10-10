import { useSyncExternalStore } from "react";

const query = "(prefers-reduced-motion: reduce)";
const key = "sidekick-motion";
const event = "sidekick-motion-change";
let sessionPreference: string | null = null;

export function readMotionPreference() {
  let preference = sessionPreference;
  try { preference = localStorage.getItem(key); } catch { /* Use the session choice when storage is unavailable. */ }
  return preference === "full" ? false : preference === "reduced" ? true : window.matchMedia(query).matches;
}

export function setMotionPreference(reduced: boolean) {
  sessionPreference = reduced ? "reduced" : "full";
  try { localStorage.setItem(key, sessionPreference); } catch { /* The current tab can still change motion. */ }
  window.dispatchEvent(new Event(event));
}

export const subscribeMotionPreference = (changed: () => void) => {
  const media = window.matchMedia(query);
  const storageChanged = (update: StorageEvent) => { if (update.key === key || update.key === null) changed(); };
  media.addEventListener("change", changed);
  window.addEventListener(event, changed);
  window.addEventListener("storage", storageChanged);
  return () => {
    media.removeEventListener("change", changed);
    window.removeEventListener(event, changed);
    window.removeEventListener("storage", storageChanged);
  };
};

// Follow the system until the user makes an explicit, app-only choice.
export function useMotionPreference() {
  return useSyncExternalStore(subscribeMotionPreference, readMotionPreference, () => false);
}
