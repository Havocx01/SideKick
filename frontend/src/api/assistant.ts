import { downloadEvidence, request } from "./client";
import type { AnalysisDetail, AnalysisRecord, AnalysisRequest, AssistantCapabilities, ConsentState } from "./types";

const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const path = (id: string) => `/api/assistant/analyses/${encodeURIComponent(id)}`;
export const assistant = {
  capabilities: (experimentId?: string | null, datasetId?: string | null) => request<AssistantCapabilities>(`/api/assistant/capabilities${datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : ""}`),
  start: (body: AnalysisRequest, reuse = true) => post<AnalysisRecord>(`/api/assistant/analyses${reuse ? "?reuse=true" : ""}`, body),
  get: (id: string) => request<AnalysisDetail>(path(id)),
  cancel: (id: string) => post<AnalysisRecord>(`${path(id)}/cancel`),
  consent: (id: string) => request<ConsentState>(`/api/assistant/consent/${encodeURIComponent(id)}`),
  setConsent: (id: string, allowed: boolean) => post<ConsentState>(`/api/assistant/consent/${encodeURIComponent(id)}`, { allowed }),
  unlock: (code: string) => post<AssistantCapabilities>("/api/assistant/access", { code }),
  saveBrief: (id: string, text: string, draftOnly = false) => request<AnalysisRecord>(`${path(id)}/brief`, { method: "POST", body: JSON.stringify({ text, draft_only: draftOnly }), keepalive: draftOnly }),
  prepareReview: (id: string) => post<AnalysisRecord>(`${path(id)}/review`),
  export: (id: string) => downloadEvidence(`${base}${path(id)}/export`, `sidekick-review-${id}.zip`)
};
