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
  DecisionReport,
  FrozenModelRecord,
  ValidationRecord,
  Partition
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

export async function downloadEvidence(url: string, filename: string) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Export failed (${response.status}). Try again.`);
  }
  const blob = await response.blob();
  const signature = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
  if (!response.headers.get("Content-Type")?.includes("application/zip") || signature.join(",") !== "80,75,3,4") {
    throw new Error("The server did not return a ZIP archive. Refresh this page and try again.");
  }
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
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
  version: string;
  can_edit_protocol: boolean;
  can_freeze: boolean;
  can_validate: boolean;
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
  matches_current_code: boolean | null;
  matches_default_config: boolean;
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

export function evidenceApi(experimentId?: string, candidate?: string, partition: Partition = "out_of_fold") {
  function scopedPath(path: string) {
    const [pathname, search] = path.split("?");
    const params = new URLSearchParams(search);
    if (experimentId) params.set("experiment_id", experimentId);
    if (candidate && !params.has("candidate")) params.set("candidate", candidate);
    if (!params.has("partition")) params.set("partition", partition);
    return `${pathname}?${params.toString()}`;
  }
  function scoped<T>(path: string, init?: RequestInit) {
    return request<T>(scopedPath(path), init);
  }
  return {
    health: () => request<HealthReport>("/api/health"),
    config: () => scoped<ConfigReport>("/api/config"),
    profile: () => scoped<DatasetProfile>("/api/profile"),
    splits: () => scoped<SplitAssignment>("/api/splits"),
    candidates: () => scoped<CandidateConfig[]>("/api/candidates"),
    selection: () => scoped<SelectionResult>("/api/selection"),
    decision: () => scoped<DecisionReport>("/api/decision"),
    exportUrl: `${BASE}${scopedPath("/api/export")}`,
    reportUrl: `${BASE}${scopedPath("/api/export/report")}`,
    paired: () => scoped<import("./types").PairedComparison[]>("/api/comparisons/paired"),
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
export interface OperationState<T> { available: boolean; record: T | null; job: ExperimentRecord | null }
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const experiments = {
  freeze: (id: string) => post<FrozenModelRecord>(`/api/experiments/${id}/freeze`),
  frozen: (id: string) => request<OperationState<FrozenModelRecord>>(`/api/experiments/${id}/freeze`),
  validate: (id: string) => post<ValidationRecord>(`/api/experiments/${id}/validation`, { untouched_confirmed: true }),
  validation: (id: string) => request<OperationState<ValidationRecord>>(`/api/experiments/${id}/validation`),
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
