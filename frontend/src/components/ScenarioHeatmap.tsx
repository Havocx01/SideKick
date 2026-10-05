import { useMemo } from "react";

import type { ScenarioResult } from "../api/types";
import { percent } from "../format";

export function ScenarioHeatmap({ results, minDetection, maxBurden, expectedEngines, onInspect }: { results: ScenarioResult[]; minDetection: number; maxBurden?: number; expectedEngines?: number; onInspect?: (rows: ScenarioResult[]) => void }) {
  const { sensors, kinds, grid } = useMemo(() => {
    const cells = new Map<string, ScenarioResult[]>();
    const sensorSet = new Set<string>();
    const kindSet = new Set<string>();

    for (const result of results) {
      if (!result.fault) continue;
      const kind =
        result.fault.kind === "drift"
          ? `drift ${result.fault.sign && result.fault.sign < 0 ? "down" : "up"}`
          : result.fault.kind;
      sensorSet.add(result.fault.sensor);
      kindSet.add(kind);
      const key = `${result.fault.sensor}|${kind}`;
      cells.set(key, [...(cells.get(key) ?? []), result]);
    }

    return { sensors: [...sensorSet].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })), kinds: [...kindSet].sort(), grid: cells };
  }, [results]);

  if (sensors.length === 0) {
    return <div className="state">No fault scenarios recorded for this candidate.</div>;
  }

  const worst = (sensor: string, kind: string): number | null => {
    const entries = grid.get(`${sensor}|${kind}`);
    if (!entries || entries.length === 0) return null;
    return Math.min(...entries.map(entry => entry.metrics.detection_fraction));
  };

  const colour = (value: number | null): string => {
    if (value === null) return "var(--canvas)";
    if (value < minDetection) {
      const depth = Math.min(1, (minDetection - value) / Math.max(0.01, minDetection));
      return `color-mix(in oklab, var(--danger) ${12 + depth * 22}%, var(--surface))`;
    }
    const headroom = Math.min(1, (value - minDetection) / Math.max(0.01, 1 - minDetection));
    return `color-mix(in oklab, var(--success) ${12 + headroom * 20}%, var(--surface))`;
  };

  return (
    <div>
      <div className="table-scroll">
        <table className="heatmap" aria-label="Worst detection by sensor and fault">
          <colgroup><col className="heat-label-column" />{kinds.map(kind => <col key={kind} />)}</colgroup>
          <thead>
            <tr>
              <th scope="col" className="heat-sensor-heading">Sensor</th>
              {kinds.map(kind => (
                <th key={kind} scope="col" className="heat-col-label">
                  {kind}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sensors.map(sensor => (
              <tr key={sensor}>
                <th scope="row" className="heat-row-label">{sensor}</th>
                {kinds.map(kind => {
                  const value = worst(sensor, kind);
                  const entries = grid.get(`${sensor}|${kind}`) ?? [];
                  const burdenFailed = entries.some(e => e.metrics.early_alarm_burden == null || (maxBurden != null && e.metrics.early_alarm_burden > maxBurden));
                  const coverageFailed = entries.some(e => e.coverage_complete === false || (expectedEngines != null && e.metrics.engines !== expectedEngines));
                  const note = coverageFailed ? "Coverage incomplete" : burdenFailed ? "Burden fails" : "";
                  return (
                    <td key={kind}>
                      <button type="button"
                        className="heat-cell"
                        style={{ background: colour(value) }}
                        aria-label={`Inspect ${sensor}, ${kind}: detection ${percent(value, 1)}${note ? `, ${note}` : ""}`}
                        onClick={() => onInspect?.(entries)}
                      >{percent(value, 1)}{note && <span className="heat-cell-note">{note}</span>}</button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heat-scale">
        <span>worse</span>
        <span className="heat-scale-ramp">
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map(fraction => (
            <span key={fraction} style={{ flex: 1, background: colour(fraction * (1 - 0)) }} />
          ))}
        </span>
        <span>better</span>
        <span className="heat-threshold">Red: below {percent(minDetection)} detection. Labels flag burden or coverage failures.</span>
      </div>
    </div>
  );
}
