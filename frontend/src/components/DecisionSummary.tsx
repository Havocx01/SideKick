import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { CandidateVerdict, SelectionResult } from "../api/types";
import { downloadEvidence } from "../api/client";
import { candidateLabel, percent } from "../format";
import { qualificationReason, ResultStory } from "./ResultStory";
import { useApi } from "../hooks/useApi";
import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { Badge, Button, Panel, StateBlock } from "./Chrome";
import { ArrowRight, ChevronRight, CircleAlert, Star } from "lucide-react";

export function EvidenceExport() {
  const api = useEvidence();
  const id = useExperimentId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setError(""); }, [id, api]);
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
        <Button variant="secondary" loading={busy} onClick={download}>Export ZIP</Button>
      </div>
      {error && <p className="state error" role="alert">{error}</p>}
    </div>
  );
}

export function DecisionSummary({ selection, inspected, inspectFaultHref }: { selection: SelectionResult; inspected?: CandidateVerdict; inspectFaultHref?: string }) {
  const id = useExperimentId();
  const chosen = selection.recommended;
  const focus = inspected ?? chosen ?? selection.ranked[0];
  const criteria = selection.criteria;
  const stage = selection.partition === "holdout" ? "final-validation" : "development";
  const query = new URLSearchParams({ partition: selection.partition ?? "out_of_fold" });
  if (focus) query.set("candidate", `${focus.candidate}/${focus.config_id}`);
  return (
    <>
      <div className="recommendation-strip" data-testid="recommendation-strip">
        <p>{chosen ? <><Star size={15} strokeWidth={2} aria-hidden="true" />Recommended: <strong>{candidateLabel(chosen.candidate, chosen.config_id)}</strong></> : <><CircleAlert size={15} strokeWidth={2} aria-hidden="true" /><strong>No model meets {stage} criteria.</strong></>}</p>
        {chosen && <Link to={`${id ? `/experiments/${id}` : ""}/comparison?${new URLSearchParams({ candidate: `${chosen.candidate}/${chosen.config_id}`, partition: selection.partition ?? "out_of_fold" })}`}>Inspect recommendation<ChevronRight size={14} aria-hidden="true" /></Link>}
      </div>
      {focus && <div data-testid="inspected-summary"><Panel title={`Inspecting: ${candidateLabel(focus.candidate, focus.config_id)}`} aside={<EvidenceExport key={id ?? "benchmark"} />}>
        <div className="qualification-row"><Badge tone={focus.qualifies ? "ok" : "bad"}>{focus.qualifies ? "Pass" : "Fail"} · {stage === "development" ? "Development" : "Final validation"}</Badge><span>{focus.required_passed} / {focus.required_scenarios} fault tests passed</span></div>
        {!focus.qualifies && <p className="qualification fails">{qualificationReason(focus)}</p>}
        <ResultStory verdict={focus} criteria={criteria} inspectFaultHref={inspectFaultHref} />
        <details className="decision-detail"><summary>Test limits</summary><p className="note">Every required case: ≥ {percent(criteria.min_detection_fraction)} warned in time; ≤ {percent(criteria.max_early_alarm_burden)} early-alarm time. {criteria.min_detection_fraction === .7 && criteria.max_early_alarm_burden === .1 ? "Demonstration settings." : ""}</p></details>
        <div className="decision-footer">
          <p className="note">Test result, not deployment approval.</p>
          <Link to={`${id ? `/experiments/${id}` : ""}/replay?${query}`}>Replay inspected model<ArrowRight size={14} aria-hidden="true" /></Link>
        </div>
      </Panel></div>}
    </>
  );
}

export function DecisionDetails() {
  const api = useEvidence();
  const report = useApi(() => api.decision(), [api]);
  const location = useLocation();
  const paired = useApi(() => api.paired(), [api]);
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
            {paired.data?.length ? (
              <div className="table-scroll paired-comparisons">
                <table>
                  <thead><tr><th>Comparison</th><th>Detection change (pp)</th><th>95% interval (pp)</th><th>Burden change (pp)</th><th>95% interval (pp)</th></tr></thead>
                  <tbody>{paired.data.map(p => (
                    <tr key={`${p.kind}/${p.first}/${p.second}`}>
                      <td>{p.first} to {p.second}<span className="note comparison-kind">{p.kind === "matched_augmentation" ? "Matched parameters and model seed" : "Selected configurations"}</span></td>
                      <td>{delta(p.detection_delta)}</td><td>{pairedInterval(p.detection_interval)}</td>
                      <td>{delta(p.burden_delta)}</td><td>{pairedInterval(p.burden_interval)}</td>
                    </tr>
                  ))}</tbody>
                </table>
                <p className="note">Second configuration minus first. Higher detection and lower burden are better. Exploratory paired equipment bootstrap; field benefit remains unestablished.</p>
              </div>
            ) : null}
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

function delta(value: number | null | undefined) {
  return value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(3)}`;
}

function pairedInterval(values: number[] | null | undefined) {
  return values?.length === 2 ? `[${values.map(delta).join(", ")}]` : "Unavailable";
}
