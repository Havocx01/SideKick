import { interval, percent } from "../format";

/**
 * A detection rate with its confidence interval, drawn to scale.
 *
 * The point estimate alone invites a comparison the data cannot support, so the
 * interval is the visual element and the point is a tick inside it. The optional
 * threshold marks the engineer's minimum, making pass and fail readable at a
 * glance without reading the number.
 */
export function IntervalBar({
  value,
  lower,
  upper,
  threshold,
}: {
  value: number;
  lower: number;
  upper: number;
  threshold?: number;
}) {
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
