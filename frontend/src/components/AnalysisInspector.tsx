import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Check, Circle, CircleAlert, Database, Download, FileText, LoaderCircle, ScanLine, ShieldCheck, Sparkles, X } from "lucide-react";
import { assistant } from "../api/assistant";
import type { AnalysisFinding, AnalysisResult, EvidenceReference } from "../api/types";
import { candidateLabel } from "../format";
import { Button, IconButton } from "./Chrome";
import { analysisError, useAnalysis } from "./AnalysisProvider";
import "./analysis.css";

export function AnalysisInspector() {
  const { open, close, context } = useAnalysis();
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal();
    title.current?.focus({ preventScroll: true });
    if (dialog.current) dialog.current.scrollTop = 0;
  }, [open, context?.task]);
  if (!open || !context) return null;
  const isBrief = context.task === "brief";
  const content = <>
    <header className="analysis-header"><div>{isBrief ? <FileText size={19} aria-hidden="true" /> : <ScanLine size={19} aria-hidden="true" />}<h2 id="analysis-title" tabIndex={-1} ref={title}>{isBrief ? "Review brief" : context.task === "data" ? "Data review" : "Analysis"}</h2></div><IconButton label="Close analysis" onClick={() => close()}><X size={17} aria-hidden="true" /></IconButton></header>
    <AnalysisContents key={JSON.stringify(context)} />
  </>;
  return <dialog ref={dialog} className={`analysis-inspector analysis-dialog${isBrief ? " review-dialog" : ""}`} aria-labelledby="analysis-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}><div className="analysis-dialog-inner">{content}</div></dialog>;
}

function AnalysisContents() {
  const { context, record, capabilities, consent, error, pending, retry, cancel, setConsent, unlock, close, saveBrief, applyMapping, prepareReview, enabled } = useAnalysis();
  const [elapsed, setElapsed] = useState(0);
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);
  const edited = useRef(false);
  const running = pending || record?.status === "queued" || record?.status === "running";
  const result = record?.result;
  useEffect(() => {
    if (!record) return;
    const sync = () => setElapsed(Math.max(0, Math.floor((running ? Date.now() / 1000 : record.updated_at) - record.created_at)));
    sync(); if (!running) return;
    const timer = window.setInterval(sync, 1000); return () => window.clearInterval(timer);
  }, [record, running]);
  useEffect(() => { edited.current = false; }, [record?.id]);
  useEffect(() => {
    if (edited.current && !record?.brief_saved_at) return;
    setDraft(record?.brief_text ?? record?.result?.brief_draft ?? ""); setSaved(Boolean(record?.brief_saved_at));
  }, [record?.id, record?.brief_text, record?.brief_saved_at, record?.result?.brief_draft]);
  if (!context) return null;
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setOperationError("");
    try { await work(); } catch (failure) { setOperationError(analysisError(failure)); } finally { setBusy(false); }
  }
  function follow() { close(false); requestAnimationFrame(() => document.getElementById("main-content")?.focus()); }
  const scopeLabel = context.partition === "holdout" ? "Final validation" : "Development";
  const consentLabel = context.task === "data" ? "dataset" : "experiment";
  return <div className="analysis-body">
    <div className="analysis-meta">
    <div className="analysis-context">{context.task === "data" ? <strong>Current column mapping</strong> : context.candidates.map(key => <strong key={key}>{candidateLabel(...key.split("/") as [string, string])}</strong>)}<span>{context.task === "data" ? "Draft data checks" : scopeLabel}{context.equipment_id ? ` · History ${context.equipment_id}` : ""}{context.cycle != null ? ` · Cycle ${context.cycle}` : ""}</span></div>
    {capabilities && <details className="analysis-access"><summary><span className="analysis-mode"><ShieldCheck size={13} aria-hidden="true" />{result?.mode === "ai" ? "AI investigation" : "Evidence analysis"}</span><span>Settings</span></summary>
      <p>{capabilities.note}</p>
      {capabilities.unlock_available && !capabilities.unlocked && <form onSubmit={event => { event.preventDefault(); void act(async () => { await unlock(code); setCode(""); }); }}><label htmlFor="presenter-code">Presenter access code</label><input id="presenter-code" type="password" autoComplete="off" value={code} onChange={event => setCode(event.target.value)} required maxLength={200} /><Button size="sm" variant="secondary" type="submit" loading={busy}>Unlock live AI</Button></form>}
      {consent && <div className="analysis-consent"><h3>Cloud analysis for this {consentLabel}</h3><p>{consent.disclosure}</p><Button size="sm" variant="secondary" loading={busy} onClick={() => void act(() => setConsent(!consent.allowed))}>{consent.allowed ? "Turn off cloud analysis" : "Allow cloud analysis"}</Button><span className="note">{consent.allowed ? `Allowed for this ${consentLabel}.` : "Off. Analysis stays on this server."}</span></div>}
      {capabilities.live_available && !running && <Button size="sm" variant="secondary" onClick={retry}>Run with AI</Button>}
    </details>}
    </div>
    {consent && !consent.allowed && <p className="analysis-local-note">Cloud analysis is off. {context.task === "data" ? "Showing local checks." : "Showing recorded evidence."}</p>}
    {(running || !result && record) && <section className="analysis-progress" aria-label="Analysis progress" aria-live="polite"><div className="analysis-progress-head"><strong>{running ? context.task === "brief" ? "Preparing review brief" : "Analyzing evidence" : record?.status === "cancelled" ? "Analysis cancelled" : record?.status === "interrupted" ? "Analysis interrupted" : "Analysis stopped"}</strong><span>{elapsed}s</span></div>{record?.stages.map(stage => <div className={`analysis-task ${stage.status}`} key={stage.id}>{stage.status === "completed" ? <Check size={14} /> : stage.status === "running" ? <LoaderCircle className="analysis-spinner" size={14} /> : stage.status === "failed" ? <CircleAlert size={14} /> : <Circle size={14} />}<span>{stage.label}</span><span className="analysis-task-state">{stage.status}</span></div>)}{running ? <Button variant="ghost" size="sm" onClick={() => void cancel()}>Cancel analysis</Button> : <Button variant="secondary" size="sm" onClick={retry}>Try again</Button>}</section>}
    {(error || record?.error || operationError) && <div className="analysis-error" role="alert"><CircleAlert size={16} /><p>{operationError || error || record?.error}</p>{error && <Button size="sm" variant="ghost" onClick={retry}>Try again</Button>}</div>}
    {!running && !record && !error && <Button variant="secondary" onClick={retry}>Run analysis</Button>}
    {result && <>
      {context.task === "brief" && record ? <div className="review-workspace">
        <section className="analysis-brief" aria-label="Review draft"><div className="review-editor-heading"><h3>Review draft</h3><span>{saved ? "Saved" : "Editable draft"}</span></div><label htmlFor="analysis-review">Edit before saving</label><textarea id="analysis-review" value={draft} maxLength={12000} rows={18} onChange={event => { edited.current = true; setDraft(event.target.value); setSaved(false); }} /><div className="review-save-row"><div className="analysis-brief-actions"><Button loading={busy} disabled={!draft.trim() || saved} onClick={() => void act(async () => { await saveBrief(draft); setSaved(true); })}>{saved ? "Saved" : "Save draft"}</Button><Button variant="secondary" disabled={!saved || busy} loading={busy} onClick={() => void act(() => assistant.export(record.id))}><Download size={16} aria-hidden="true" />Export brief</Button></div><p className="note" role="status">{saved ? "Saved as an engineer review draft." : "Save your edits to include them in the export."}</p></div></section>
        <aside className="review-reference" aria-label="Brief references"><h3>Supporting evidence</h3><Assessment result={result} follow={follow} /><details><summary>Findings · {result.findings.length}</summary>{result.findings.map(finding => <Finding key={finding.id} finding={finding} />)}{result.interpretation && <Interpretation result={result} />}</details><details><summary>Sources · {result.sources.length}</summary><EvidenceSources sources={result.sources} follow={follow} /></details><NextChecks result={result} follow={follow} /><ResultLimits result={result} /></aside>
      </div> : <ResultContent result={result} follow={follow} candidates={context.candidates} task={context.task} />}
      {!running && record?.status === "completed" && context.task === "data" && result.suggested_mapping && <section className="analysis-mapping" aria-label="Suggested mapping"><h3>Suggested column roles</h3><dl><div><dt>Equipment</dt><dd>{result.suggested_mapping.equipment_id}</dd></div><div><dt>Cycle</dt><dd>{result.suggested_mapping.cycle_index}</dd></div><div><dt>Failure</dt><dd>{result.suggested_mapping.failure_cycle || "Requires your confirmation"}</dd></div><div><dt>Sensors</dt><dd>{result.suggested_mapping.sensors.join(", ")}</dd></div></dl><Button variant="secondary" disabled={busy} onClick={applyMapping}>Use draft mapping</Button><p className="note">Review the roles before confirming.</p></section>}
      {!running && record?.status === "completed" && context.task !== "data" && context.task !== "brief" && enabled("brief") && <div className="analysis-brief-actions"><Button size="sm" variant="secondary" loading={busy} onClick={() => void act(prepareReview)}><FileText size={15} aria-hidden="true" />Add to review brief</Button></div>}
      {result.investigation?.length ? <details className="analysis-queries"><summary>Investigation · {result.investigation.length} checks</summary><ol className="investigation-log">{result.investigation.map((call, index) => <li key={`${index}-${call.name}`}>{call.label}<span>{call.source_ids.length ? `${call.source_ids.length} references` : "Case lookup"}</span></li>)}</ol></details> : null}
      <details className="analysis-audit"><summary>Analysis record</summary><div className="analysis-tool-chips" aria-label="Completed stages">{record?.stages.filter(s => s.status === "completed").map(s => <span key={s.id}><Check size={12} />{s.label}</span>)}</div><details className="analysis-queries"><summary>{queries(result).length} evidence queries</summary><div className="analysis-tool-chips">{queries(result).map(query => <span key={query}><Database size={12} />{query}</span>)}</div></details><p>{result.verification}</p><p>{result.model ? `Model: ${result.model} · Prompt ${result.prompt_version}` : `Generated from recorded evidence · Prompt ${result.prompt_version}`}</p><p>Evidence: <code>{result.evidence_digest.slice(0, 16)}</code></p>{result.fallback_reason && <p>{result.fallback_reason}</p>}</details>
    </>}
  </div>;
}

function queries(result: AnalysisResult) {
  return [...new Set(result.sources.map(source => `${source.label} · ${source.context.split(" · ").slice(1).join(" · ")}`))];
}
const COMPARED: [string, string][] = [["qualifies", "Meets limits"], ["required_passed", "Required cases passed"], ["clean_detection", "Healthy: warned in time"], ["clean_early_alarm_burden", "Healthy: early alarm time"], ["worst_burden_required", "Worst fault early alarm"], ["mean_detection_required", "Average fault detection"]];
function ComparisonTable({ result, candidates }: { result: AnalysisResult; candidates: string[] }) {
  const value = (candidate: string, metric: string) => result.sources.find(source => source.candidate === candidate && source.metric === metric);
  const rows = COMPARED.filter(([metric]) => candidates.every(candidate => value(candidate, metric)));
  return <div className="table-scroll analysis-compare"><table><caption className="sr-only">Selected model comparison</caption><thead><tr><th scope="col">Measure</th>{candidates.map(candidate => <th scope="col" className="num" key={candidate}>{candidate.split("/")[1]}</th>)}</tr></thead>
    <tbody>{rows.map(([metric, label]) => <tr key={metric}><th scope="row">{label}</th>{candidates.map(candidate => <td className="num" key={candidate}>{value(candidate, metric)!.display}{metric === "required_passed" && value(candidate, "required_scenarios") ? ` / ${value(candidate, "required_scenarios")!.display}` : ""}</td>)}</tr>)}</tbody></table></div>;
}

function ResultContent({ result, follow, candidates, task }: { result: AnalysisResult; follow: () => void; candidates: string[]; task: string }) {
  return <div className="analysis-layout">
    <div className="analysis-main">
    <Assessment result={result} follow={follow} />
    <section className="analysis-findings" aria-label="Finding"><h3>{task === "compare" ? "Comparison" : task === "data" ? "Data checks" : "Recorded result"}</h3>{result.findings[0] ? <Finding finding={result.findings[0]} /> : <p>{result.summary}</p>}
      {task === "compare" && candidates.length === 2 && <ComparisonTable result={result} candidates={candidates} />}
      {result.interpretation && <Interpretation result={result} />}
      {result.findings.length > 1 && <details><summary>{result.findings.length - 1} more findings</summary>{result.findings.slice(1).map(finding => <Finding key={finding.id} finding={finding} />)}</details>}</section>
    <NextChecks result={result} follow={follow} />
    <ResultLimits result={result} />
    </div>
    <section className="analysis-evidence" aria-label="Evidence"><h3>Evidence <span>{result.sources.length}</span></h3><EvidenceSources sources={result.sources} follow={follow} /></section>
  </div>;
}
function Assessment({ result, follow }: { result: AnalysisResult; follow: () => void }) {
  if (!result.assessment?.length) return null;
  const citation = (source: EvidenceReference) => <Link key={source.id} to={source.href} onClick={follow}>{source.label}: {source.display}<ArrowUpRight size={12} aria-hidden="true" /></Link>;
  return <section className="analysis-assessment" aria-label="Assessment"><h3>Assessment</h3>{result.assessment.map(claim => {
    const sources = claim.source_ids.map(id => result.sources.find(source => source.id === id)).filter((source): source is EvidenceReference => Boolean(source));
    return <article key={claim.id}><p>{claim.text}</p><div className="assessment-citations">{sources.slice(0, 2).map(citation)}</div>{sources.length > 2 && <details><summary>{sources.length - 2} more references</summary><div className="assessment-citations">{sources.slice(2).map(citation)}</div></details>}</article>;
  })}</section>;
}
function Interpretation({ result }: { result: AnalysisResult }) {
  return <div className="analysis-interpretation"><span className="analysis-generated"><Sparkles size={12} aria-hidden="true" />AI interpretation · verify against evidence</span><p>{result.interpretation}</p></div>;
}
function EvidenceSources({ sources, follow }: { sources: EvidenceReference[]; follow: () => void }) {
  return <><div className="analysis-source-list">{sources.slice(0, 6).map(source => <Source key={source.id} source={source} follow={follow} />)}</div>{sources.length > 6 && <details><summary>All sources · {sources.length}</summary>{sources.slice(6).map(source => <Source key={source.id} source={source} follow={follow} />)}</details>}</>;
}
function NextChecks({ result, follow }: { result: AnalysisResult; follow: () => void }) {
  return result.actions[0] ? <section className="analysis-next" aria-label="Next check"><h3>Next check</h3><p>{result.actions[0].detail}</p><Link to={result.actions[0].href} onClick={follow}>{result.actions[0].label}<ArrowRight size={14} aria-hidden="true" /></Link>{result.actions.length > 1 && <details><summary>Other checks</summary>{result.actions.slice(1).map(action => <div className="analysis-other-check" key={action.id}><p>{action.detail}</p><Link to={action.href} onClick={follow}>{action.label}<ArrowUpRight size={13} aria-hidden="true" /></Link></div>)}</details>}</section> : null;
}
function ResultLimits({ result }: { result: AnalysisResult }) {
  return result.limitations.length ? <details className="analysis-limits"><summary>What this does not establish</summary><ul>{result.limitations.map(item => <li key={item}>{item}</li>)}</ul></details> : null;
}
function Finding({ finding }: { finding: AnalysisFinding }) {
  return <article className={`analysis-insight ${finding.tone ?? "neutral"}`}><h4>{finding.tone === "success" ? <Check size={15} /> : finding.tone === "danger" || finding.tone === "warning" ? <CircleAlert size={15} /> : <ScanLine size={15} />}{finding.title}</h4><p>{finding.detail}</p></article>;
}
function Source({ source, follow }: { source: EvidenceReference; follow: () => void }) {
  return <Link className="analysis-source" to={source.href} onClick={follow}><div><strong>{source.label}</strong><span className="analysis-source-value">{source.display}</span><ArrowUpRight size={14} aria-hidden="true" /></div><small>{source.context}</small></Link>;
}
