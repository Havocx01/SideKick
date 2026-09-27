import type {
  AlertExplanation,
  CalibrationReport,
  CandidateConfig,
  DatasetProfile,
  ReplaySeries,
  ReproducibilityCheck,
  RunRecord,
  ScenarioResult,
  SelectionResult,
  SplitAssignment,
  DatasetRegistration,
  DatasetConfirmation,
  ExperimentRecord,
  ExperimentCreate,
  DecisionReport
} from "./types";

// Vite proxies /api when no base URL is configured.
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Sidekick-Request": "1", ...init?.headers }
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail);
    } catch (error) {
      console.warn("Could not read the server error response.", error);
      detail = undefined;
    }
    throw new ApiError(
      response.status === 503
        ? "No evidence is available from this deployment."
        : `Request failed (${response.status})`,
      response.status,
      detail
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
  mode: "full" | "replay" | "demo";
  can_train: boolean;
  can_upload: boolean;
  sample_equipment: number;
  sample_configurations: number;
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
  source_digest: string | null;
  holdout_status: string;
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

export function evidenceApi(experimentId?: string) {
  function scoped<T>(path: string, init?: RequestInit) {
    const separator = path.includes("?") ? "&" : "?";
    const url = experimentId ? `${path}${separator}experiment_id=${encodeURIComponent(experimentId)}` : path;
    return request<T>(url, init);
  }
  return {
    health: () => request<HealthReport>("/api/health"),
    config: () => scoped<ConfigReport>("/api/config"),
    profile: () => scoped<DatasetProfile>("/api/profile"),
    splits: () => scoped<SplitAssignment>("/api/splits"),
    candidates: () => scoped<CandidateConfig[]>("/api/candidates"),
    selection: () => scoped<SelectionResult>("/api/selection"),
    decision: () => scoped<DecisionReport>("/api/decision"),
    exportUrl: `${BASE}/api/export${query({ experiment_id: experimentId })}`,
    finalEvaluation: () =>
      scoped<{ available: boolean; note?: string; selection?: SelectionResult }>("/api/final-evaluation"),
    scenarios: (options: { candidate?: string; requiredOnly?: boolean; includeClean?: boolean } = {}) =>
      scoped<ScenarioResult[]>(
        `/api/scenarios${query({
          candidate: options.candidate,
          required_only: options.requiredOnly,
          include_clean: options.includeClean
        })}`
      ),
    calibration: () => scoped<CalibrationReport[]>("/api/calibration"),
    replayIndex: () =>
      scoped<{ series: ReplayIndexEntry[]; equipment: string[]; scenarios: string[] }>("/api/replay/index"),
    replay: (equipmentId?: string, scenarioId?: string) =>
      scoped<ReplaySeries[]>(`/api/replay${query({ equipment_id: equipmentId, scenario_id: scenarioId })}`),
    explanations: (equipmentId?: string) =>
      scoped<AlertExplanation[]>(`/api/explanations${query({ equipment_id: equipmentId })}`),
    limitations: () => scoped<{ limitations: string[] }>("/api/limitations"),
    runs: (kind?: string) => scoped<RunRecord[]>(`/api/runs${query({ kind })}`),
    run: (runId: string) => scoped<RunRecord>(`/api/runs/${runId}`),
    reproducibility: () =>
      scoped<{ available: boolean; note?: string; check?: ReproducibilityCheck }>("/api/reproducibility")
  };
}

export const api = evidenceApi();
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const experiments = {
  sample: () => post<DatasetRegistration>("/api/datasets/sample"),
  upload: (file: File) =>
    request<DatasetRegistration>("/api/datasets/upload", {
      method: "POST",
      body: file,
      headers: { "Content-Type": "text/csv", "X-Filename": encodeURIComponent(file.name) }
    }),
  dataset: (id: string) => request<DatasetRegistration>(`/api/datasets/${id}`),
  confirm: (id: string, body: DatasetConfirmation) => post<DatasetRegistration>(`/api/datasets/${id}/confirm`, body),
  create: (body: ExperimentCreate) => post<ExperimentRecord>("/api/experiments", body),
  list: () => request<ExperimentRecord[]>("/api/experiments"),
  get: (id: string) => request<ExperimentRecord>(`/api/experiments/${id}`),
  cancel: (id: string) => post<ExperimentRecord>(`/api/experiments/${id}/cancel`)
};
