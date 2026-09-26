import type { CalibrationReport } from "../api/types";
import { candidateLabel, number } from "../format";

export function ReliabilityPlot({ reports }: { reports: CalibrationReport[] }) {
  const size = 300;
  const margin = 34;
  const plot = size - margin * 2;

  const palette = ["var(--clean)", "var(--fault)", "var(--ok)", "var(--warn)"];

  const x = (value: number) => margin + value * plot;
  const y = (value: number) => margin + plot - value * plot;

  return (
    <div>
      <svg
        className="chart"
        viewBox={`0 0 ${size} ${size}`}
        style={{ maxWidth: size }}
        role="img"
        aria-label="Reliability plot"
      >
        {[0, 0.25, 0.5, 0.75, 1].map(tick => (
          <g key={tick}>
            <line className="gridline" x1={x(0)} x2={x(1)} y1={y(tick)} y2={y(tick)} />
            <line className="gridline" x1={x(tick)} x2={x(tick)} y1={y(0)} y2={y(1)} />
            <text x={margin - 6} y={y(tick) + 3} textAnchor="end">
              {tick}
            </text>
            <text x={x(tick)} y={size - margin + 14} textAnchor="middle">
              {tick}
            </text>
          </g>
        ))}

        {/* Perfect calibration. */}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--line-strong)" strokeDasharray="4 3" />

        {reports.map((report, index) => {
          const colour = palette[index % palette.length];
          const path = report.bins
            .map(
              (bin, position) =>
                `${position === 0 ? "M" : "L"}${x(Math.min(1, bin.mean_predicted)).toFixed(1)},${y(bin.observed_rate).toFixed(1)}`
            )
            .join(" ");
          return (
            <g key={`${report.candidate}/${report.config_id}`}>
              <path d={path} fill="none" stroke={colour} strokeWidth={1.6} />
              {report.bins.map(bin => (
                <circle
                  key={bin.lower}
                  cx={x(Math.min(1, bin.mean_predicted))}
                  cy={y(bin.observed_rate)}
                  // Radius carries how much data supports the point.
                  r={Math.max(2, Math.min(6, Math.sqrt(bin.count) / 6))}
                  fill={colour}
                  opacity={0.8}
                >
                  <title>
                    {`predicted ${number(bin.mean_predicted)}, observed ${number(bin.observed_rate)}, ${bin.count} cycles`}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}

        <text x={size / 2} y={size - 4} textAnchor="middle">
          mean predicted score
        </text>
        <text x={10} y={size / 2} textAnchor="middle" transform={`rotate(-90 10 ${size / 2})`}>
          observed failure rate
        </text>
      </svg>
      <div className="legend">
        {reports.map((report, index) => (
          <span className="legend-item" key={`${report.candidate}/${report.config_id}`}>
            <span className="legend-swatch" style={{ background: palette[index % palette.length] }} />
            {candidateLabel(report.candidate, report.config_id)} — Brier {number(report.brier, 4)}
          </span>
        ))}
        <span className="legend-item">point size shows how many cycles fell in the band</span>
      </div>
    </div>
  );
}
