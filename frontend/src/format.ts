export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function number(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

export function integer(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString();
}

export function cycles(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${Math.round(value)} cyc`;
}

export function interval(lower: number, upper: number): string {
  return `${percent(lower)}–${percent(upper)}`;
}

export function candidateLabel(candidate: string, configId?: string): string {
  const names: Record<string, string> = {
    xgboost: "XGBoost",
    xgboost_augmented: "Augmented XGBoost",
    logistic_regression: "Logistic regression",
    age_baseline: "Age baseline"
  };
  const pretty = names[candidate] ?? candidate.replace(/_/g, " ");
  return configId ? `${pretty} · ${configId}` : pretty;
}

export function candidateKey(candidate: string, configId: string): string {
  return `${candidate}/${configId}`;
}

export function scenarioLabel(scenarioId: string): string {
  if (scenarioId === "clean") return "No fault";
  const parts = scenarioId.split("-");
  const [kind, duration, ...rest] = parts;
  const sensor = rest.filter(part => !/^(on\d+|onrand|sd[\d.]+|pos|neg|len\d+)$/.test(part)).join("-");
  const onset = rest.find(part => /^on/.test(part));
  const severity = rest.find(part => /^sd/.test(part));
  const sign = rest.find(part => part === "pos" || part === "neg");

  const channel = sensor.replace(/^sensor_(\d+)$/, "Sensor $1").replace(/^op_setting_(\d+)$/, "Operating setting $1");
  const bits = [kind === "stuck" ? "frozen reading" : kind === "dropout" ? "missing readings" : kind, channel];
  if (severity) bits.push(`${severity.slice(2)} SD ${sign === "neg" ? "down" : "up"}`);
  bits.push(duration === "transient" ? "temporary" : "persistent");
  if (onset === "onrand") bits.push("random onset");
  else if (onset) bits.push(`starts ${onset.slice(2)} cycles before failure`);
  return bits.filter(Boolean).join(" · ");
}

export function scenarioSummary(scenarioId: string): string {
  const [kind = "", channel, severity] = scenarioLabel(scenarioId).split(" · ");
  const fault = kind.charAt(0).toUpperCase() + kind.slice(1);
  return [channel, fault, scenarioId.startsWith("drift-") ? severity : null].filter(Boolean).join(" · ");
}
