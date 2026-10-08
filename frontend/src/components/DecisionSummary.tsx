import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { AcceptanceCriteria, CandidateVerdict, SelectionResult } from "../api/types";
import { downloadEvidence } from "../api/client";
import { candidateLabel, percent } from "../format";
import { useAnalysis } from "./AnalysisProvider";
import { ResultStory, WarningBreakdown, WarningDefinitions } from "./ResultStory";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/registry/components/accordion/accordion";
import { useApi } from "../hooks/useApi";
import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { Badge, Button, IconButton, Panel, StateBlock } from "./Chrome";
import { Check, ChevronRight, ClipboardList, Download, FileText, ScanLine, Star, X } from "lucide-react";

export function EvidenceExport({ labels = false }: { labels?: boolean } = {}) {
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
        <a className={labels ? "button" : "action-icon"} href={api.reportUrl} target="_blank" rel="noopener noreferrer" aria-label="Open report" title="Open report"><FileText size={17} aria-hidden="true" />{labels && "Open report"}</a>
        {labels ? <Button variant="secondary" loading={busy} onClick={download}><Download size={17} aria-hidden="true" />Download evidence</Button>
          : <IconButton label="Export ZIP" loading={busy} onClick={download}><Download size={17} aria-hidden="true" /></IconButton>}
      </div>
      {error && <p className="state error" role="alert">{error}</p>}
    </div>
  );
}

export function DecisionSummary({ selection, inspected, inspectFaultHref }: { selection: SelectionResult; inspected?: CandidateVerdict; inspectFaultHref?: string }) {
  const id = useExperimentId();
  const api = useEvidence();
  const report = useApi(() => api.decision(), [api]);
  const analysis = useAnalysis();
  const chosen = selection.recommended;
  const focus = inspected ?? chosen ?? selection.ranked[0];
  const criteria = selection.criteria;
  const stage = selection.partition === "holdout" ? "final-validation" : "development";
  const query = new URLSearchParams({ partition: selection.partition ?? "out_of_fold" });
  if (focus) query.set("candidate", `${focus.candidate}/${focus.config_id}`);
  return (
    <>
      <section className={`recommendation-strip${chosen ? "" : " none"}`} data-testid="recommendation-strip" aria-label="Recommendation">
        <div className="recommendation-text">
          <span className="recommendation-label">{chosen && <Star size={16} fill="currentColor" aria-hidden="true" />}{chosen ? "Recommended model" : "No recommendation"}</span>
          <span className="recommendation-name">{chosen ? candidateLabel(chosen.candidate, chosen.config_id) : `No model meets ${stage} criteria.`}</span>
        </div>
        {chosen && (focus?.candidate !== chosen.candidate || focus.config_id !== chosen.config_id) &&
          <Link className="result-text-link" to={`${id ? `/experiments/${id}` : ""}/comparison?${new URLSearchParams({ candidate: `${chosen.candidate}/${chosen.config_id}`, partition: selection.partition ?? "out_of_fold" })}`}>Inspect recommendation<ChevronRight size={14} aria-hidden="true" /></Link>}
      </section>
      {focus && <div className="model-result" data-testid="inspected-summary"><Panel title={candidateLabel(focus.candidate, focus.config_id)} aside={<EvidenceExport key={id ?? "benchmark"} />}>
        <div className="qualification-row"><Badge tone={focus.qualifies ? "ok" : "bad"}><span className="verdict-badge">{focus.qualifies ? <Check size={12} aria-hidden="true" /> : <X size={12} aria-hidden="true" />}{focus.qualifies ? "Pass" : "Fail"}</span></Badge><span className="qualification-stage">{stage === "development" ? "Development" : "Final validation"}</span><span>{focus.required_passed} / {focus.required_scenarios} fault tests passed</span></div>
        {!focus.qualifies && <p className="qualification fails compact-reason">{qualificationSummary(focus, criteria)}</p>}
        <ResultStory verdict={focus} criteria={criteria} inspectFaultHref={inspectFaultHref} compact />
        <Accordion key={`${id}/${selection.partition}/${focus.candidate}/${focus.config_id}`} type="single" collapsible className="result-details">
          <AccordionItem value="details">
            <AccordionTrigger>Result details</AccordionTrigger>
            <AccordionContent>
              <div className="result-details-content">
                <div className="result-details-grid">
                  <section className="result-outcomes" aria-label="Warning outcomes"><h3>Warning outcomes</h3><WarningBreakdown verdict={focus} /></section>
                  <div className="result-detail-context">
                    <section className="result-explanation" aria-label="Qualification reason">
                      <h3>{focus.qualifies ? "Why it passed" : "Why it failed"}</h3>
                      <StateBlock loading={report.loading} error={report.error}>
                        {report.data?.inspected_candidate === `${focus.candidate}/${focus.config_id}` && report.data.partition === selection.partition &&
                          <p>{report.data.qualification_reason}</p>}
                      </StateBlock>
                    </section>
                    <section className="result-test-settings" aria-label="Test limits">
                      <h3>Test limits</h3>
                      <dl><div><dt>Minimum in time</dt><dd>{percent(criteria.min_detection_fraction)}</dd></div><div><dt>Maximum early alarm time</dt><dd>{percent(criteria.max_early_alarm_burden)}</dd></div></dl>
                      {criteria.min_detection_fraction === .7 && criteria.max_early_alarm_burden === .1 && <p className="note">Demonstration settings. Each required case must pass.</p>}
                    </section>
                  </div>
                </div>
                <WarningDefinitions verdict={focus} criteria={criteria} />
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
        <div className="result-analysis-actions">
          {analysis.enabled("investigate") && <Button variant="secondary" onClick={() => analysis.start({ task: "investigate", experiment_id: id, partition: selection.partition, candidates: [`${focus.candidate}/${focus.config_id}`] })}><ScanLine size={15} aria-hidden="true" />{focus.qualifies ? "Analyze result" : "Investigate failure"}</Button>}
          {/* <Link className="result-text-link" to={`${id ? `/experiments/${id}` : ""}/replay?${query}`}>Replay model</Link> */}
          {analysis.enabled("brief") && <Button variant="secondary" onClick={() => analysis.start({ task: "brief", experiment_id: id, partition: selection.partition, candidates: [`${focus.candidate}/${focus.config_id}`] })}><ClipboardList size={15} aria-hidden="true" />Prepare review brief</Button>}
        </div>
        <p className="note decision-note">Test result, not deployment approval.</p>
      </Panel></div>}
    </>
  );
}

function qualificationSummary(verdict: CandidateVerdict, criteria: AcceptanceCriteria) {
  const reasons: string[] = [];
  if (verdict.clean.detection_fraction < criteria.min_detection_fraction || (verdict.required_scenarios > 0 && verdict.worst_detection_required < criteria.min_detection_fraction)) {
    reasons.push(`Detection below the ${percent(criteria.min_detection_fraction)} minimum.`);
  }
  if ((verdict.clean.early_alarm_burden != null && verdict.clean.early_alarm_burden > criteria.max_early_alarm_burden) || (verdict.required_scenarios > 0 && verdict.worst_burden_required != null && verdict.worst_burden_required > criteria.max_early_alarm_burden)) {
    reasons.push(`Early alarm time above the ${percent(criteria.max_early_alarm_burden)} limit.`);
  }
  return reasons.join(" ") || "Some required results are missing or incomplete.";
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
            <details className="decision-detail disclosure-plain">
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
