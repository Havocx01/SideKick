import { ApiError } from "../../api/client";
import type { Finding } from "../../api/types";
import type { Tone } from "../Chrome";

export interface Component { sensor: string; kind: string; onset_before_failure?: number | null; severity_sd?: number | null; sign?: number | null; length?: number | null }

export const errorText = (error: unknown) => error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Request failed. Try again.";
export const histories = (count: number) => `${count} ${count === 1 ? "history" : "histories"}`;
export const requestId = () => crypto.randomUUID().replace(/-/g, "");

export const stops: Record<string, [string, Tone]> = {
  completed: ["All proposals run", "ok"], model_stopped: ["Nemotron stopped", "info"], budget_exhausted: ["Experiment budget used", "warn"],
  experiment_limit: ["Experiment budget used", "warn"], failure_limit: ["Failure limit reached", "bad"], cancelled: ["Cancelled", "neutral"],
  time_limit: ["Time limit reached", "warn"], evaluator_budget: ["Evaluator limit reached", "warn"], call_limit: ["Provider call limit reached", "warn"],
  token_limit: ["Token allowance used", "warn"], proposal_limit: ["Proposal limit reached", "warn"], input_limit: ["Input limit reached", "warn"],
  provider_error: ["Provider error", "bad"], invalid_response: ["Invalid provider response", "bad"]
};

export const findingTones: Record<Finding["status"], [string, Tone]> = {
  measured_failure: ["Measured failure", "bad"], no_measured_failure: ["No measured failure", "ok"], inconclusive: ["Inconclusive", "warn"],
  not_applicable: ["Not applicable", "neutral"], invalid_proposal: ["Rejected proposal", "neutral"], execution_error: ["Execution error", "bad"]
};

const sensorNames: Record<string, string> = { temp_bearing: "Bearing temperature", vibration_rms: "Vibration", oil_particles: "Oil particles", pressure_out: "Outlet pressure", flow_rate: "Flow rate", current_draw: "Current draw" };
const faultNames: Record<string, string> = { dropout: "missing readings", stuck: "held constant", drift: "drifting" };
const effectNames: Record<string, string> = { late_warnings: "warned late", missed_warnings: "missed the warning", alarm_burden: "raised more early alarms" };

const components = (scenario: Record<string, unknown> | null | undefined) => (scenario?.components ?? []) as Component[];

export function describeCase(scenario: Record<string, unknown> | null | undefined) {
  const items = components(scenario);
  if (!items.length) return "Unreadable case";
  return items.map(item => {
    const drift = item.kind === "drift" && item.severity_sd ? ` ${item.sign === -1 ? "−" : "+"}${item.severity_sd} SD` : "";
    const timing = item.onset_before_failure ? ` from ${item.onset_before_failure} cycles before failure` : " at a seeded onset";
    return `${item.sensor} ${item.kind}${drift}${item.length ? ` for ${item.length} cycles` : ""}${timing}`;
  }).join(" + ");
}

export function caseTitle(scenario: Record<string, unknown> | null | undefined) {
  const items = components(scenario);
  return items.length ? items.map(item => `${sensorNames[item.sensor] ?? item.sensor.replace(/_/g, " ")}: ${faultNames[item.kind] ?? item.kind}`).join(" + ") : "Unreadable fault test";
}

export const faultKinds = (scenario: Record<string, unknown> | null | undefined) => [...new Set(components(scenario).map(item => item.kind))].sort().join(" ");
export const effectText = (kind: string, count: number) => `${histories(count)} ${effectNames[kind] ?? kind.replace(/_/g, " ")}`;
