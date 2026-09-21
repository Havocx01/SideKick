import type { ReplaySeries } from "../api/types";

interface Props {
  series: ReplaySeries;
  comparison?: ReplaySeries | null;
  height?: number;
}

const MARGIN = { top: 14, right: 16, bottom: 26, left: 40 };

/**
 * The score for one engine against cycles remaining, read right to left towards
 * failure at zero.
 *
 * Three things are drawn together because the question is how they relate: the
 * score, the threshold it is compared against, and the shaded useful window in
 * which a warning would have been actionable. Alert episodes are shaded so a
 * viewer can see whether the alert was up during that window without tracing the
 * curve against the line.
 */
export function ScoreTimeline({ series, comparison, height = 220 }: Props) {
  const width = 760;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points;
  if (points.length === 0) return <div className="state">This history has no scorable cycles.</div>;

  const maxRul = Math.max(...points.map((p) => p.rul));
  const allScores = [...points.map((p) => p.score), ...(comparison?.points ?? []).map((p) => p.score)];
  const maxScore = Math.max(series.threshold * 1.15, ...allScores);
  const minScore = Math.min(0, ...allScores);

  // Remaining life decreases over time, so the axis runs from maxRul down to 0.
  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (score: number) =>
    MARGIN.top + plotHeight - ((score - minScore) / Math.max(1e-9, maxScore - minScore)) * plotHeight;

  const path = (items: typeof points) =>
    items.map((p, index) => `${index === 0 ? "M" : "L"}${x(p.rul).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");

  const usefulLeft = x(30);
  const usefulRight = x(10);

  const episodeBands = series.episodes.map((episode) => {
    const left = x(episode.start_rul);
    const right = x(episode.end_rul);
    return { left, width: Math.max(1.5, right - left), key: `${episode.start_cycle}-${episode.end_cycle}` };
  });

  const ticks = [maxRul, Math.round(maxRul * 0.75), Math.round(maxRul * 0.5), 45, 30, 10, 0].filter(
    (tick, index, all) => tick <= maxRul && all.indexOf(tick) === index,
  );

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Score over time for ${series.equipment_id}`}>
        {/* Useful warning window: late enough to be a real signal, early enough to act on. */}
        <rect
          x={usefulLeft}
          y={MARGIN.top}
          width={Math.max(1, usefulRight - usefulLeft)}
          height={plotHeight}
          fill="var(--ok-soft)"
        />
        <text x={(usefulLeft + usefulRight) / 2} y={MARGIN.top - 4} textAnchor="middle">
          useful window
        </text>

        {episodeBands.map((band) => (
          <rect
            key={band.key}
            x={band.left}
            y={MARGIN.top}
            width={band.width}
            height={plotHeight}
            fill="var(--fault)"
            opacity={0.1}
          />
        ))}

        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const value = minScore + fraction * (maxScore - minScore);
          return (
            <g key={fraction}>
              <line
                className="gridline"
                x1={MARGIN.left}
                x2={width - MARGIN.right}
                y1={y(value)}
                y2={y(value)}
              />
              <text x={MARGIN.left - 6} y={y(value) + 3} textAnchor="end">
                {value.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Threshold the alert rule compares against. */}
        <line
          x1={MARGIN.left}
          x2={width - MARGIN.right}
          y1={y(series.threshold)}
          y2={y(series.threshold)}
          stroke="var(--fault)"
          strokeWidth={1.25}
          strokeDasharray="5 3"
        />
        <text x={width - MARGIN.right} y={y(series.threshold) - 4} textAnchor="end" fill="var(--fault)">
          threshold {series.threshold.toFixed(3)}
        </text>

        {comparison ? (
          <path d={path(comparison.points)} fill="none" stroke="var(--clean)" strokeWidth={1.5} opacity={0.55} />
        ) : null}
        <path
          d={path(points)}
          fill="none"
          stroke={series.fault ? "var(--fault)" : "var(--clean)"}
          strokeWidth={1.9}
        />

        <g className="axis">
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={MARGIN.top + plotHeight}
            y2={MARGIN.top + plotHeight}
          />
          {ticks.map((tick) => (
            <text key={tick} x={x(tick)} y={height - 8} textAnchor="middle">
              {tick}
            </text>
          ))}
          <text x={width / 2} y={height + 6} textAnchor="middle" opacity={0} >
            cycles remaining
          </text>
        </g>
      </svg>
      <div className="legend">
        <span className="legend-item">
          <span
            className="legend-swatch"
            style={{ background: series.fault ? "var(--fault)" : "var(--clean)" }}
          />
          {series.fault ? "score with the fault injected" : "score on the original readings"}
        </span>
        {comparison ? (
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: "var(--clean)", opacity: 0.55 }} />
            score on the original readings
          </span>
        ) : null}
        <span className="legend-item" style={{ color: "var(--fault)" }}>
          <span className="legend-swatch dashed" />
          alert threshold
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--fault)", opacity: 0.18, height: 10 }} />
          alert active
        </span>
        <span className="legend-item">horizontal axis: cycles remaining before failure</span>
      </div>
    </div>
  );
}

/** The sensor under test, original against altered, on the same time axis. */
export function SensorTrace({ series, height = 150 }: { series: ReplaySeries; height?: number }) {
  const width = 760;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points.filter((p) => p.sensor_clean !== null || p.sensor_faulted !== null);
  if (points.length === 0) return null;

  const values = points.flatMap((p) =>
    [p.sensor_clean, p.sensor_faulted].filter((v): v is number => v !== null),
  );
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(1e-9, maxValue - minValue);
  const maxRul = Math.max(...series.points.map((p) => p.rul));

  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (value: number) => MARGIN.top + plotHeight - ((value - minValue) / span) * plotHeight;

  const path = (pick: (p: (typeof points)[number]) => number | null) => {
    let started = false;
    return points
      .map((p) => {
        const value = pick(p);
        // A dropout leaves a genuine gap, so the line breaks rather than
        // interpolating across readings that were never taken.
        if (value === null) {
          started = false;
          return "";
        }
        const command = started ? "L" : "M";
        started = true;
        return `${command}${x(p.rul).toFixed(1)},${y(value).toFixed(1)}`;
      })
      .join(" ");
  };

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Readings for ${series.fault?.sensor ?? "sensor"}`}>
        <path
          d={path((p) => p.sensor_clean ?? null)}
          fill="none"
          stroke="var(--clean)"
          strokeWidth={1.5}
        />
        <path
          d={path((p) => p.sensor_faulted ?? null)}
          fill="none"
          stroke="var(--fault)"
          strokeWidth={1.8}
        />
        <g className="axis">
          <line
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={MARGIN.top + plotHeight}
            y2={MARGIN.top + plotHeight}
          />
          <text x={MARGIN.left - 6} y={y(maxValue) + 3} textAnchor="end">
            {maxValue.toFixed(1)}
          </text>
          <text x={MARGIN.left - 6} y={y(minValue) + 3} textAnchor="end">
            {minValue.toFixed(1)}
          </text>
        </g>
      </svg>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--clean)" }} />
          original reading
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--fault)" }} />
          altered reading{series.fault ? ` — ${series.fault.sensor}` : ""}
        </span>
        <span className="legend-item">gaps are cycles where the sensor reported nothing</span>
      </div>
    </div>
  );
}
