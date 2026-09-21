import type {
  AlertExplanation,
  CalibrationReport,
  CandidateConfig,
  CopilotAnswer,
  DatasetProfile,
  ReplaySeries,
  ReproducibilityCheck,
  RunRecord,
  ScenarioResult,
  SelectionResult,
  SplitAssignment,
} from "./types";

/** Empty in development, where Vite proxies /api to the local backend. */
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail);
    } catch {
      detail = undefined;
    }
    // 503 means the evidence bundle is missing, which is a setup problem with a
    // known fix, so the message carries it through to the interface.
    throw new ApiError(
      response.status === 503
        ? "No evidence is available from this deployment."
        : `Request failed (${response.status})`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export interface HealthReport {
  status: string;
  mode: "full" | "replay";
  can_train: boolean;
  copilot: string;
  note: string;
  bundle: {
    available: boolean;
    dataset_id?: string;
    config_fingerprint?: string;
    generated_at?: string;
    scenario_results?: number;
    replay_series?: number;
  };
}

export interface ConfigReport {
  config: Record<string, unknown>;
  config_fingerprint: string;
  git_commit: string | null;
  current_code_fingerprint: string;
  matches_current_code: boolean;
}

export interface ReplayIndexEntry {
  equipment_id: string;
  candidate: string;
  config_id: string;
  scenario_id: string;
  fault: string | null;
  detected: boolean;
  late: boolean;
  missed: boolean;
  lead_time: number | null;
  episodes: number;
  cycles: number;
}

export interface CopilotStatus {
  language_model: string | null;
  available: boolean;
  max_tool_calls: number;
  mode: string;
  note: string;
}

export interface ToolDescriptor {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  mutating: boolean;
}

export const api = {
  health: () => request<HealthReport>("/api/health"),
  config: () => request<ConfigReport>("/api/config"),
  profile: () => request<DatasetProfile>("/api/profile"),
  splits: () => request<SplitAssignment>("/api/splits"),
  candidates: () => request<CandidateConfig[]>("/api/candidates"),
  selection: () => request<SelectionResult>("/api/selection"),
  finalEvaluation: () =>
    request<{ available: boolean; note?: string; selection?: SelectionResult }>(
      "/api/final-evaluation",
    ),
  scenarios: (options: { candidate?: string; requiredOnly?: boolean; includeClean?: boolean } = {}) =>
    request<ScenarioResult[]>(
      `/api/scenarios${query({
        candidate: options.candidate,
        required_only: options.requiredOnly,
        include_clean: options.includeClean,
      })}`,
    ),
  calibration: () => request<CalibrationReport[]>("/api/calibration"),
  replayIndex: () =>
    request<{ series: ReplayIndexEntry[]; equipment: string[]; scenarios: string[] }>(
      "/api/replay/index",
    ),
  replay: (equipmentId?: string, scenarioId?: string) =>
    request<ReplaySeries[]>(
      `/api/replay${query({ equipment_id: equipmentId, scenario_id: scenarioId })}`,
    ),
  explanations: (equipmentId?: string) =>
    request<AlertExplanation[]>(`/api/explanations${query({ equipment_id: equipmentId })}`),
  limitations: () => request<{ limitations: string[] }>("/api/limitations"),
  runs: (kind?: string) => request<RunRecord[]>(`/api/runs${query({ kind })}`),
  run: (runId: string) => request<RunRecord>(`/api/runs/${runId}`),
  reproducibility: () =>
    request<{ available: boolean; note?: string; check?: ReproducibilityCheck }>(
      "/api/reproducibility",
    ),
  copilotStatus: () => request<CopilotStatus>("/api/copilot/status"),
  copilotTools: () => request<{ tools: ToolDescriptor[]; note: string }>("/api/copilot/tools"),
  copilotSuggestions: () => request<{ suggestions: string[] }>("/api/copilot/suggestions"),
  askCopilot: (question: string) =>
    request<CopilotAnswer>("/api/copilot", {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};
