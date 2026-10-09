export type ProtocolView = "overview" | "sensors" | "technical";
export type WarningZone = "early" | "transition" | "timely" | "late";
export interface TimingZone { id: WarningZone; label: string; range: string; explanation: string }

export function protocolView(value: string | null): ProtocolView {
  return value === "sensors" || value === "technical" ? value : "overview";
}

export function protocolSearch(previous: URLSearchParams, view: string): URLSearchParams {
  const next = new URLSearchParams(previous);
  next.set("view", protocolView(view));
  return next;
}

export function recordedNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function protocolTiming(config: Record<string, unknown>) {
  const min = recordedNumber(config.min_useful_lead);
  const horizon = recordedNumber(config.horizon_cycles);
  const late = recordedNumber(config.late_window_end);
  const boundary = recordedNumber(config.transition_band_end);
  const unavailable = { available: false, zones: [] as TimingZone[], gap: null as string | null,
    note: "Warning timing is unavailable: the recorded boundaries are missing or inconsistent. See the recorded scoring rules." };
  if (min == null || horizon == null || late == null || boundary == null ||
    ![min, horizon, late, boundary].every(Number.isInteger) || min < 1 || horizon <= min || late < 0 || late >= min || boundary <= horizon) return unavailable;
  const range = (from: number, to: number) => from === to ? String(from) : `${from}–${to}`;
  return { available: true, note: "", gap: late + 1 < min ? range(late + 1, min - 1) : null,
    zones: [
      { id: "early", label: "Early", range: `${boundary + 1}+`, explanation: `Above ${boundary} cycles before failure, time spent in an active warning contributes to early-alarm burden.` },
      { id: "transition", label: "Transition", range: range(horizon + 1, boundary), explanation: `Cycles ${range(horizon + 1, boundary)} are outside the useful window and excluded from early-alarm burden.` },
      { id: "timely", label: "In time", range: range(min, horizon), explanation: `A warning active between ${min} and ${horizon} cycles before failure counts as in time, including both boundaries.` },
      { id: "late", label: "Late", range: late > 0 ? range(1, late) : "None", explanation: late > 0
        ? `If no warning was active in the useful window, an active warning ${range(1, late)} cycles before failure counts as late.`
        : "No late-warning window is recorded. A history without a timely warning counts as missed." }
    ] as TimingZone[] };
}

export function splitIntegrity(splits: { development: string[]; holdout: string[] }): string | null {
  const development = new Set(splits.development), reserved = new Set(splits.holdout);
  if (development.size !== splits.development.length || reserved.size !== splits.holdout.length) return "Equipment assignments contain repeated identifiers. Inspect the recorded assignments.";
  if ([...development].some(id => reserved.has(id))) return "Some equipment appears in both development and reserved validation. Inspect the recorded assignments.";
  return null;
}
