import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { SelectionResult } from "../api/types";
import { downloadEvidence } from "../api/client";
import { candidateLabel, integer, percent } from "../format";
import { useApi } from "../hooks/useApi";
import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { Button, Panel, StateBlock } from "./Chrome";

function EvidenceExport() {
  const api = useEvidence();
  const id = useExperimentId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setError(""); }, [id]);
  async function download() {
    setBusy(true);
    setError("");
    try {
      await downloadEvidence(api.exportUrl, `sidekick-${id ?? "benchmark"}-evidence.zip`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Export failed. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="evidence-export">
      <div className="export-actions">
        <a href={api.reportUrl} target="_blank" rel="noopener noreferrer">Open report</a>
        <Button loading={busy} onClick={download}>Export ZIP</Button>
      </div>
      {error && <p className="state error" role="alert">{error}</p>}
    </div>
  );
}

export function DecisionSummary({ selection }: { selection: SelectionResult }) {
  const id = useExperimentId();
  const chosen = selection.recommended;
  const criteria = selection.criteria;
  return (
    <Panel title={chosen ? `${candidateLabel(chosen.candidate, chosen.config_id)} meets the criteria` : "No model qualified"} aside={<EvidenceExport key={id ?? "benchmark"} />}>
      {chosen ? (
        <dl className="decision-metrics">
          <div><dt>Clean detection</dt><dd>{integer(chosen.clean.detected)} / {integer(chosen.clean.engines)} <span>({percent(chosen.clean.detection_fraction, 1)})</span></dd></div>
          <div><dt>Worst required detection</dt><dd>{chosen.worst_metrics ? `${integer(chosen.worst_metrics.detected)} / ${integer(chosen.worst_metrics.engines)}` : "Not tested"} <span>({percent(chosen.worst_detection_required, 1)})</span></dd></div>
          <div><dt>Required cases passed</dt><dd>{integer(chosen.required_passed)} / {integer(chosen.required_scenarios)}</dd></div>
        </dl>
      ) : <p>No candidate passed every required case. Inspect the failures below.</p>}
      <p className="note decision-rule">
        Required in every case: detection ≥ {percent(criteria.min_detection_fraction)} · early-alarm burden ≤ {percent(criteria.max_early_alarm_burden)}.
        {chosen ? ` Clean alarm burden: ${percent(chosen.clean.early_alarm_burden, 2)}.` : ""}
      </p>
      <div className="decision-footer">
        <p className="note">Development evidence only; deployment is not approved.{selection.uncertain_comparisons?.length ? " Leading models remain closely matched." : ""}</p>
        <Link to={`${id ? `/experiments/${id}` : ""}/replay`}>Replay the {chosen ? "recommended" : "leading"} model</Link>
      </div>
    </Panel>
  );
}

export function DecisionDetails() {
  const api = useEvidence();
  const report = useApi(() => api.decision(), [api]);
  const location = useLocation();
  useEffect(() => {
    if (location.hash === "#augmentation" && report.data) document.getElementById("augmentation")?.scrollIntoView();
  }, [location.hash, report.data]);
  return (
    <StateBlock loading={report.loading} error={report.error}>
      {report.data && (
        <div id="augmentation" className="evidence-section">
          <Panel title="Did fault-augmented training help?">
            {report.data.unaugmented && report.data.augmented && (
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Qualifying configuration</th><th>Clean detection</th><th>Mean fault detection</th><th>Worst fault detection</th><th>Clean alarm burden</th></tr></thead>
                  <tbody>
                    {[report.data.unaugmented, report.data.augmented].map(v => (
                      <tr key={`${v.candidate}/${v.config_id}`}>
                        <td>{candidateLabel(v.candidate, v.config_id)}</td>
                        {[v.clean.detection_fraction, v.mean_detection_required, v.worst_detection_required, v.clean.early_alarm_burden].map((n, i) => (<td key={i}>{percent(n, 2)}</td>))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <details className="decision-detail">
              <summary>Interpret the augmentation comparison</summary>
              <p>{report.data.augmentation_summary}</p>
            </details>
            <details className="decision-detail">
              <summary>Selection rule and weakest required case</summary>
              <p>{report.data.summary}</p><p>{report.data.fault_summary}</p>
            </details>
            <details className="decision-detail">
              <summary>Evaluation limits</summary>
              <ul>{report.data.limitations.map(t => (<li key={t}>{t}</li>))}</ul>
            </details>
          </Panel>
        </div>
      )}
    </StateBlock>
  );
}
