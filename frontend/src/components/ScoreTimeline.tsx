import type { ReplaySeries } from "../api/types";

interface Props {
  series: ReplaySeries;
  comparison?: ReplaySeries | null;
  height?: number;
  horizon?: number;
  minLead?: number;
  cursorCycle?: number;
}

const MARGIN = { top: 26, right: 24, bottom: 46, left: 64 };
const WIDTH = 760;

function niceMax(value: number) {
  if (value > 0.5) return Math.max(1, Math.ceil(value * 4) / 4);
  return Math.ceil(value * 20) / 20 || 1;
}

function tickLabel(value: number) {
  return Number(value.toFixed(2)).toString();
}

function cycleTicks(maxRul: number, horizon: number, minLead: number) {
  return [maxRul, Math.round(maxRul * 0.75), Math.round(maxRul * 0.5), horizon, minLead, 0].filter(
    (tick, index, all) => tick <= maxRul && all.indexOf(tick) === index
  );
}

function CycleAxis({ x, ticks, y, height }: { x: (rul: number) => number; ticks: number[]; y: number; height: number }) {
  return (
    <g className="axis">
      <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y} y2={y} />
      {ticks.map(tick => (
        <text key={tick} x={x(tick)} y={y + 16} textAnchor="middle">{tick}</text>
      ))}
      <text x={MARGIN.left + (WIDTH - MARGIN.left - MARGIN.right) / 2} y={height - 6} textAnchor="middle">Cycles before failure</text>
    </g>
  );
}

export function ScoreTimeline({ series, comparison, height = 240, horizon = 30, minLead = 10, cursorCycle }: Props) {
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points;
  if (points.length === 0) return <div className="state">This history has no scorable cycles.</div>;

  const maxRul = Math.max(...points.map(p => p.rul));
  const allScores = [...points.map(p => p.score), ...(comparison?.points ?? []).map(p => p.score)];
  const maxScore = niceMax(Math.max(series.threshold * 1.1, ...allScores));
  const minScore = Math.min(0, ...allScores);

  // Remaining life decreases over time, so the axis runs from maxRul down to 0.
  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (score: number) =>
    MARGIN.top + plotHeight - ((score - minScore) / Math.max(1e-9, maxScore - minScore)) * plotHeight;

  const path = (items: typeof points) =>
    items.map((p, index) => `${index === 0 ? "M" : "L"}${x(p.rul).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");

  const usefulLeft = x(Math.min(horizon, maxRul));
  const usefulRight = x(Math.min(minLead, maxRul));
  const lineColor = series.fault ? "var(--fault)" : "var(--clean)";

  const cursor = points.find(point => point.cycle === cursorCycle);
  const visible = (items: typeof points) => cursorCycle == null ? items : items.filter(point => point.cycle <= cursorCycle);
  const episodeBands = series.episodes.filter(episode => cursorCycle == null || episode.start_cycle <= cursorCycle).map(episode => {
    const left = x(episode.start_rul);
    const right = x(cursor && episode.end_cycle > cursor.cycle ? cursor.rul : episode.end_rul);
    return { left, width: Math.max(2, right - left), key: `${episode.start_cycle}-${episode.end_cycle}` };
  });

  return (
    <div className="replay-chart">
      <div className="chart-scroll" tabIndex={0} aria-label="Scrollable score chart">
        <svg
          className="chart"
          viewBox={`0 0 ${WIDTH} ${height}`}
          role="img"
          aria-label={`Score over time for ${series.equipment_id}`}
        >
          <text x={14} y={MARGIN.top + plotHeight / 2} textAnchor="middle" transform={`rotate(-90 14 ${MARGIN.top + plotHeight / 2})`}>Warning score</text>
          {/* Useful warning window: late enough to be a real signal, early enough to act on. */}
          <rect x={usefulLeft} y={MARGIN.top} width={Math.max(1, usefulRight - usefulLeft)} height={plotHeight} fill="var(--ok-soft)" rx={3} />
          <text className="chart-label" x={(usefulLeft + usefulRight) / 2} y={MARGIN.top - 8} textAnchor="middle" style={{ fill: "var(--ok)" }}>Useful window</text>

          {[0, 0.25, 0.5, 0.75, 1].map(fraction => {
            const value = minScore + fraction * (maxScore - minScore);
            return (
              <g key={fraction}>
                {fraction > 0 && <line className="gridline" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(value)} y2={y(value)} />}
                <text x={MARGIN.left - 8} y={y(value) + 3.5} textAnchor="end">{tickLabel(value)}</text>
              </g>
            );
          })}

          {/* Threshold the alert rule compares against. */}
          <line x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(series.threshold)} y2={y(series.threshold)} stroke="var(--text-secondary)" strokeWidth={1} strokeDasharray="4 4" />
          <text className="chart-label" x={MARGIN.left + 6} y={y(series.threshold) - 6}>Alert threshold {series.threshold.toFixed(3)}</text>

          {comparison ? (
            <path d={path(visible(comparison.points))} fill="none" stroke="var(--clean)" strokeWidth={1.75} strokeDasharray="5 3" strokeLinejoin="round" />
          ) : null}
          <path d={path(visible(points))} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

          {series.fault && series.fault_onset_rul != null && series.fault_onset_rul <= maxRul && (
            <g>
              <line x1={x(series.fault_onset_rul)} x2={x(series.fault_onset_rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} stroke="var(--warn)" strokeDasharray="3 3" />
              <text className="chart-label" x={x(series.fault_onset_rul) - 6} y={MARGIN.top + 14} textAnchor="end" style={{ fill: "var(--warn)" }}>Fault begins</text>
            </g>
          )}

          {/* Active warnings drawn as a strip under the plot, so they never tint the window. */}
          {episodeBands.map(band => (
            <rect key={band.key} x={band.left} y={MARGIN.top + plotHeight - 4} width={band.width} height={4} rx={2} fill={lineColor} />
          ))}
          {cursor && (
            <g>
              <line className="replay-cursor" x1={x(cursor.rul)} x2={x(cursor.rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />
              <circle cx={x(cursor.rul)} cy={y(cursor.score)} r={4} fill="var(--surface)" stroke={lineColor} strokeWidth={2} />
            </g>
          )}

          <CycleAxis x={x} ticks={cycleTicks(maxRul, horizon, minLead)} y={MARGIN.top + plotHeight} height={height} />
        </svg>
      </div>
      <div className="legend">
        <span className="legend-item"><span className="legend-swatch" style={{ background: lineColor }} />{series.fault ? "Faulted" : "Original"}</span>
        {comparison ? <span className="legend-item"><span className="legend-swatch dashed" style={{ color: "var(--clean)" }} />Original</span> : null}
        <span className="legend-item"><span className="legend-swatch dashed" style={{ color: "var(--text-secondary)" }} />Alert threshold</span>
        <span className="legend-item"><span className="legend-swatch area" style={{ background: "var(--ok-soft)", boxShadow: "inset 0 0 0 1px color-mix(in oklab, var(--ok) 30%, transparent)" }} />Useful window</span>
        <span className="legend-item"><span className="legend-swatch" style={{ background: lineColor, height: 4 }} />Warning active</span>
        {series.fault && <span className="legend-item"><span className="legend-swatch dashed" style={{ color: "var(--warn)" }} />Fault begins</span>}
      </div>
    </div>
  );
}

export function SensorTrace({ series, height = 200, cursorCycle }: { series: ReplaySeries; height?: number; cursorCycle?: number }) {
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points.filter(p => p.sensor_clean != null || p.sensor_faulted != null);
  if (points.length === 0) return null;

  const values = points.flatMap(p => [p.sensor_clean, p.sensor_faulted].filter((v): v is number => v != null));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(1e-9, maxValue - minValue);
  const maxRul = Math.max(...series.points.map(p => p.rul));
  const onset = series.fault_onset_rul != null && series.fault_onset_rul <= maxRul ? series.fault_onset_rul : null;

  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (value: number) => MARGIN.top + plotHeight - ((value - minValue) / span) * plotHeight;

  const path = (pick: (p: (typeof points)[number]) => number | null, from?: number | null) => {
    let started = false;
    return points.filter(p => (cursorCycle == null || p.cycle <= cursorCycle) && (from == null || p.rul <= from))
      .map(p => {
        const value = pick(p);
        // Break the line at missing readings instead of interpolating across the gap.
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
  const cursor = series.points.find(p => p.cycle === cursorCycle);

  return (
    <div className="replay-chart">
      <div className="chart-scroll" tabIndex={0} aria-label="Scrollable sensor chart">
        <svg
          className="chart"
          viewBox={`0 0 ${WIDTH} ${height}`}
          role="img"
          aria-label={`Readings for ${series.fault?.sensor ?? "sensor"}`}
        >
          {onset != null && (
            <g>
              <rect x={x(onset)} y={MARGIN.top} width={Math.max(1, x(0) - x(onset))} height={plotHeight} fill="var(--fault-soft)" rx={3} />
              <text className="chart-label" x={x(onset) + 6} y={MARGIN.top - 8} style={{ fill: "var(--fault)" }}>Fault</text>
            </g>
          )}
          <line className="gridline" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(maxValue)} y2={y(maxValue)} />
          <path d={path(p => p.sensor_clean ?? null)} fill="none" stroke="var(--clean)" strokeWidth={1.5} strokeLinejoin="round" />
          <path d={path(p => p.sensor_faulted ?? null, onset)} fill="none" stroke="var(--fault)" strokeWidth={1.75} strokeLinejoin="round" />
          {cursor && <line className="replay-cursor" x1={x(cursor.rul)} x2={x(cursor.rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />}
          <text x={MARGIN.left - 8} y={y(maxValue) + 3.5} textAnchor="end">{maxValue.toFixed(1)}</text>
          <text x={MARGIN.left - 8} y={y(minValue) + 3.5} textAnchor="end">{minValue.toFixed(1)}</text>
          <CycleAxis x={x} ticks={cycleTicks(maxRul, 30, 10)} y={MARGIN.top + plotHeight} height={height} />
        </svg>
      </div>
      <div className="legend">
        <span className="legend-item"><span className="legend-swatch" style={{ background: "var(--clean)" }} />Original</span>
        <span className="legend-item"><span className="legend-swatch" style={{ background: "var(--fault)" }} />Faulted</span>
        <span className="legend-item">Gaps = missing readings</span>
      </div>
    </div>
  );
}
