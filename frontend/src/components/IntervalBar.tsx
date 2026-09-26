import { interval, percent } from "../format";

export function IntervalBar({ value, lower, upper, threshold }: { value: number; lower: number; upper: number; threshold?: number; }) {
  const clamp = (x: number) => Math.max(0, Math.min(1, x));
  const left = clamp(lower) * 100;
  const width = Math.max(1.5, (clamp(upper) - clamp(lower)) * 100);

  return (
    <div
      className="interval"
      title={`${percent(value, 1)} (95% interval ${interval(lower, upper)})`}
      role="img"
      aria-label={`Detection ${percent(value, 1)}, 95% interval ${interval(lower, upper)}`}
    >
      <div className="interval-range" style={{ left: `${left}%`, width: `${width}%` }} />
      <div className="interval-point" style={{ left: `${clamp(value) * 100}%` }} />
      {threshold !== undefined ? (
        <div className="interval-threshold" style={{ left: `${clamp(threshold) * 100}%` }} />
      ) : null}
    </div>
  );
}
