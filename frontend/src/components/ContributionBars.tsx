import type { AlertExplanation } from "../api/types";
import { number } from "../format";

/**
 * What moved this model's score at one cycle.
 *
 * Deliberately titled as model behaviour rather than diagnosis. Under an injected
 * fault these attributions usually point at the corrupted channel, which tells you
 * how much the model leaned on it, not what is physically wrong with the machine.
 */
export function ContributionBars({ explanation }: { explanation: AlertExplanation }) {
  if (!explanation.available || (explanation.contributions ?? []).length === 0) {
    return <p className="note">{explanation.note}</p>;
  }

  const contributions = explanation.contributions ?? [];
  const largest = Math.max(...contributions.map((c) => Math.abs(c.contribution)), 1e-9);

  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th className="num">Value</th>
            <th style={{ width: 190 }}>Effect on the score</th>
            <th className="num">Contribution</th>
          </tr>
        </thead>
        <tbody>
          {contributions.map((contribution) => {
            const magnitude = (Math.abs(contribution.contribution) / largest) * 100;
            const raises = contribution.contribution >= 0;
            return (
              <tr key={contribution.feature}>
                <td className="mono">{contribution.feature}</td>
                <td className="num">{number(contribution.value, 3)}</td>
                <td>
                  {/* Centre line: bars to the right raise the score, to the left lower it. */}
                  <div style={{ display: "flex", alignItems: "center", height: 14 }}>
                    <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
                      {!raises ? (
                        <div
                          style={{
                            width: `${magnitude}%`,
                            height: 10,
                            background: "var(--clean)",
                            opacity: 0.75,
                            borderRadius: "2px 0 0 2px",
                          }}
                        />
                      ) : null}
                    </div>
                    <div style={{ width: 1, height: 14, background: "var(--line-strong)" }} />
                    <div style={{ flex: 1 }}>
                      {raises ? (
                        <div
                          style={{
                            width: `${magnitude}%`,
                            height: 10,
                            background: "var(--fault)",
                            opacity: 0.75,
                            borderRadius: "0 2px 2px 0",
                          }}
                        />
                      ) : null}
                    </div>
                  </div>
                </td>
                <td className="num">{number(contribution.contribution, 3)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="legend">
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--fault)" }} />
          pushes the score up
        </span>
        <span className="legend-item">
          <span className="legend-swatch" style={{ background: "var(--clean)" }} />
          pushes the score down
        </span>
        {explanation.base_value !== null && explanation.base_value !== undefined ? (
          <span className="legend-item">baseline {number(explanation.base_value, 3)}</span>
        ) : null}
      </div>
      <p className="note" style={{ marginTop: 10 }}>
        {explanation.note}
      </p>
    </div>
  );
}
