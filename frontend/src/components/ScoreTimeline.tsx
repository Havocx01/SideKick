import type { ReplaySeries } from "../api/types";

interface Props {
  series: ReplaySeries;
  comparison?: ReplaySeries | null;
  height?: number;
  horizon?: number;
  minLead?: number;
  cursorCycle?: number;
}

const MARGIN = { top: 24, right: 24, bottom: 30, left: 68 };

export function ScoreTimeline({ series, comparison, height = 220, horizon = 30, minLead = 10, cursorCycle }: Props) {
  const width = 760;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points;
  if (points.length === 0) return <div className="state">This history has no scorable cycles.</div>;

  const maxRul = Math.max(...points.map(p => p.rul));
  const allScores = [...points.map(p => p.score), ...(comparison?.points ?? []).map(p => p.score)];
  const maxScore = Math.max(series.threshold * 1.15, ...allScores);
  const minScore = Math.min(0, ...allScores);

  // Remaining life decreases over time, so the axis runs from maxRul down to 0.
  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (score: number) =>
    MARGIN.top + plotHeight - ((score - minScore) / Math.max(1e-9, maxScore - minScore)) * plotHeight;

  const path = (items: typeof points) =>
    items.map((p, index) => `${index === 0 ? "M" : "L"}${x(p.rul).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");

  const usefulLeft = x(Math.min(horizon, maxRul));
  const usefulRight = x(Math.min(minLead, maxRul));

  const cursor = points.find(point => point.cycle === cursorCycle);
  const visible = (items: typeof points) => cursorCycle == null ? items : items.filter(point => point.cycle <= cursorCycle);
  const episodeBands = series.episodes.filter(episode => cursorCycle == null || episode.start_cycle <= cursorCycle).map(episode => {
    const left = x(episode.start_rul);
    const right = x(cursor && episode.end_cycle > cursor.cycle ? cursor.rul : episode.end_rul);
    return { left, width: Math.max(1.5, right - left), key: `${episode.start_cycle}-${episode.end_cycle}` };
  });

  const ticks = [maxRul, Math.round(maxRul * 0.75), Math.round(maxRul * 0.5), horizon, minLead, 0].filter(
    (tick, index, all) => tick <= maxRul && all.indexOf(tick) === index
  );

  return (
    <div>
      <div className="chart-scroll" tabIndex={0} aria-label="Scrollable score chart">
        <svg
          className="chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Score over time for ${series.equipment_id}`}
        >
          <text x={16} y={MARGIN.top + plotHeight / 2} textAnchor="middle" transform={`rotate(-90 16 ${MARGIN.top + plotHeight / 2})`}>Model warning score</text>
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

          {episodeBands.map(band => (
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

          {[0, 0.25, 0.5, 0.75, 1].map(fraction => {
            const value = minScore + fraction * (maxScore - minScore);
            return (
              <g key={fraction}>
                <line className="gridline" x1={MARGIN.left} x2={width - MARGIN.right} y1={y(value)} y2={y(value)} />
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
            stroke="var(--text-secondary)"
            strokeWidth={1.25}
            strokeDasharray="5 3"
          />
          <text x={width - MARGIN.right} y={y(series.threshold) - 4} textAnchor="end">
            Alert threshold {series.threshold.toFixed(3)}
          </text>

          {comparison ? (
            <path d={path(visible(comparison.points))} fill="none" stroke="var(--clean)" strokeWidth={2} strokeDasharray="6 3" />
          ) : null}
          <path
            d={path(visible(points))}
            fill="none"
            stroke={series.fault ? "var(--fault)" : "var(--clean)"}
            strokeWidth={1.9}
          />
          {cursor && <line className="replay-cursor" x1={x(cursor.rul)} x2={x(cursor.rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />}

          {series.fault && series.fault_onset_rul != null && series.fault_onset_rul <= maxRul && (
            <g>
              <line x1={x(series.fault_onset_rul)} x2={x(series.fault_onset_rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} stroke="var(--warn)" strokeDasharray="3 3" />
              <text x={x(series.fault_onset_rul) - 4} y={MARGIN.top + 12} textAnchor="end" fill="var(--warn)">Fault begins</text>
            </g>
          )}

          <g className="axis">
            <line
              x1={MARGIN.left}
              x2={width - MARGIN.right}
              y1={MARGIN.top + plotHeight}
              y2={MARGIN.top + plotHeight}
            />
            {ticks.map(tick => (
              <text key={tick} x={x(tick)} y={height - 8} textAnchor="middle">
                {tick}
              </text>
            ))}
          </g>
        </svg>
      </div>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: series.fault ? "var(--fault)" : "var(--clean)" }} />
          {series.fault ? "Faulted" : "Original"}
        </span>
        {comparison ? (
          <span className="legend-item">
            <span className="legend-swatch dashed" style={{ color: "var(--clean)" }} />
            Original
          </span>
        ) : null}
        <span className="legend-item" style={{ color: "var(--text-secondary)" }}>
          <span className="legend-swatch dashed" />
          Alert threshold
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--fault)", opacity: 0.18, height: 10 }} />
          Warning active
        </span>
        {series.fault && <span className="legend-item" style={{ color: "var(--warn)" }}><span className="legend-swatch dashed" />fault begins</span>}
      </div>
      <p className="chart-axis-label">Cycles before failure</p>
    </div>
  );
}

export function SensorTrace({ series, height = 180, cursorCycle }: { series: ReplaySeries; height?: number; cursorCycle?: number }) {
  const width = 760;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const points = series.points.filter(p => p.sensor_clean != null || p.sensor_faulted != null);
  if (points.length === 0) return null;

  const values = points.flatMap(p => [p.sensor_clean, p.sensor_faulted].filter((v): v is number => v != null));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(1e-9, maxValue - minValue);
  const maxRul = Math.max(...series.points.map(p => p.rul));

  const x = (rul: number) => MARGIN.left + ((maxRul - rul) / Math.max(1, maxRul)) * plotWidth;
  const y = (value: number) => MARGIN.top + plotHeight - ((value - minValue) / span) * plotHeight;

  const path = (pick: (p: (typeof points)[number]) => number | null) => {
    let started = false;
    return points.filter(p => cursorCycle == null || p.cycle <= cursorCycle)
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

  return (
    <div>
      <div className="chart-scroll" tabIndex={0} aria-label="Scrollable sensor chart">
        <svg
          className="chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Readings for ${series.fault?.sensor ?? "sensor"}`}
        >
          <path d={path(p => p.sensor_clean ?? null)} fill="none" stroke="var(--clean)" strokeWidth={1.5} />
          <path d={path(p => p.sensor_faulted ?? null)} fill="none" stroke="var(--fault)" strokeWidth={1.8} />
          {series.points.find(p => p.cycle === cursorCycle) && <line className="replay-cursor" x1={x(series.points.find(p => p.cycle === cursorCycle)!.rul)} x2={x(series.points.find(p => p.cycle === cursorCycle)!.rul)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />}
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
      </div>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--clean)" }} />
          Original
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--fault)" }} />
          Faulted
        </span>
        <span className="legend-item">Gaps = missing readings</span>
      </div>
    </div>
  );
}
