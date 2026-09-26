import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { Panel, StateBlock } from "./Chrome";

export function DecisionSummary() {
  const api = useEvidence();
  const id = useExperimentId();
  const report = useApi(() => api.decision(), [api]);
  return (
    <StateBlock loading={report.loading} error={report.error}>
      {report.data && (
        <Panel
          title={report.data.title}
          aside={
            <a className="button primary" href={api.exportUrl}>
              Export evidence
            </a>
          }
        >
          <p>{report.data.summary}</p>
          <p>{report.data.fault_summary}</p>
          <p className="note">
            Detection: equipment warned 10 to 30 cycles before failure. Early-alarm burden: the share of eligible
            healthy cycles spent in an alert, more than 45 cycles before failure. Warning time is in cycles, not hours.
          </p>
          <Link to={`${id ? `/experiments/${id}` : ""}/replay`}>See how the warnings change for one machine</Link>
          <div id="augmentation" className="decision-detail">
            <h3>Did fault-augmented training help?</h3>
            <p>{report.data.augmentation_summary}</p>
            {report.data.unaugmented && report.data.augmented && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Qualifying configuration</th>
                      <th>Clean detection</th>
                      <th>Mean fault detection</th>
                      <th>Worst fault detection</th>
                      <th>Clean alarm burden</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[report.data.unaugmented, report.data.augmented].map(v => (
                      <tr key={v.config_id}>
                        <td>
                          {v.candidate}/{v.config_id}
                        </td>
                        {[
                          v.clean.detection_fraction,
                          v.mean_detection_required,
                          v.worst_detection_required,
                          v.clean.early_alarm_burden
                        ].map((n, i) => (
                          <td key={i}>{(n * 100).toFixed(2)}%</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <details className="decision-detail">
            <summary>What this experiment does not establish</summary>
            <ul>
              {report.data.limitations.map(t => (<li key={t}>{t}</li>))}
            </ul>
          </details>
        </Panel>
      )}
    </StateBlock>
  );
}
