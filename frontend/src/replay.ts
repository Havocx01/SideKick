import type { AlertEpisode, EngineOutcome } from "./api/types";

export function outcomeLabel(outcome: EngineOutcome): { tone: "ok" | "warn" | "bad"; text: string } {
  if (outcome.detected) {
    return {
      tone: "ok",
      text: outcome.lead_time == null ? "useful warning" : `useful warning, ${outcome.lead_time} cycles ahead`
    };
  }
  if (outcome.late) return { tone: "warn", text: "warned too late" };
  return { tone: "bad", text: "missed the useful warning window" };
}

export function episodeLabel(episode: Pick<AlertEpisode, "start_rul" | "end_rul">, horizon: number, minLead: number) {
  if (episode.start_rul >= minLead && episode.end_rul <= horizon) return "active in the useful window";
  if (episode.end_rul > horizon) return "ended before the useful window";
  return "too late to act";
}
