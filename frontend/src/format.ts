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
  const pretty = candidate.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
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

  const bits = [kind === "stuck" ? "stuck reading" : kind, sensor];
  if (severity) bits.push(`${severity.slice(2)} SD ${sign === "neg" ? "down" : "up"}`);
  if (duration === "transient") bits.push("transient");
  if (onset === "onrand") bits.push("random onset");
  else if (onset) bits.push(`from ${onset.slice(2)} cyc`);
  return bits.filter(Boolean).join(" · ");
}
