import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, CircleAlert, Cpu, Database, Download, FileText, RotateCcw, ScanLine, X } from "lucide-react";
import { assistant } from "../api/assistant";
import type { AnalysisFinding, AnalysisResult, EvidenceReference } from "../api/types";
import { candidateLabel } from "../format";
import { Button, IconButton } from "./Chrome";
import { analysisError, useAnalysis } from "./AnalysisProvider";
import { AssistantThinkingState, EvidenceCitation, EvidenceContextCards, StreamingText, streamWords, useStreamingReveal } from "./AssistantElements";
import "./analysis.css";

export function AnalysisInspector() {
  const { open, close, context, record, pending, error } = useAnalysis();
  const loading = !error && !record?.error && (pending || record?.status === "queued" || record?.status === "running");
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
    <header className="analysis-header"><div>{isBrief ? <FileText size={19} aria-hidden="true" /> : <ScanLine size={19} aria-hidden="true" />}<h2 id="analysis-title" tabIndex={-1} ref={title}>{isBrief ? "Review brief" : context.task === "data" ? "Data review" : "Analysis"}</h2></div><IconButton label={loading ? "Cancel analysis" : "Close analysis"} onClick={() => close()}><X size={17} aria-hidden="true" /></IconButton></header>
    <AnalysisContents key={JSON.stringify(context)} />
  </>;
  return <dialog ref={dialog} className={`analysis-inspector analysis-dialog${isBrief ? " review-dialog" : ""}`} aria-labelledby="analysis-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}><div className="analysis-dialog-inner">{content}</div></dialog>;
}

function AnalysisContents() {
  const { context, record, capabilities, consent, error, pending, retry, setConsent, unlock, close, saveBrief, editBrief, applyMapping, prepareReview, enabled } = useAnalysis();
  const [elapsed, setElapsed] = useState(0);
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);
  const edited = useRef(false);
  const running = pending || record?.status === "queued" || record?.status === "running";
  const result = !running && record?.status === "completed" ? record.result : undefined;
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
  const candidates = context.candidates ?? [];
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setOperationError("");
    try { await work(); } catch (failure) { setOperationError(analysisError(failure)); } finally { setBusy(false); }
  }
  function follow() { close(false); requestAnimationFrame(() => document.getElementById("main-content")?.focus()); }
  const scopeLabel = context.partition === "holdout" ? "Final validation" : "Development";
  const consentLabel = context.task === "data" ? "dataset" : "experiment";
  const thinking = running && !error && !record?.error;
  const stages = record?.stages ?? [];
  return <div className={`analysis-body${thinking ? " analysis-loading-body" : ""}`}>
    <div className="analysis-meta">
    <div className="analysis-context">{context.task === "data" ? <strong>Current column mapping</strong> : candidates.map(key => <strong key={key}>{candidateLabel(...key.split("/") as [string, string])}</strong>)}<span><span>{context.task === "data" ? "Draft data checks" : scopeLabel}{context.equipment_id ? ` · History ${context.equipment_id}` : ""}{context.cycle != null ? ` · Cycle ${context.cycle}` : ""}</span>{result && <span className="analysis-mode">{result.mode === "ai" ? <Cpu size={14} strokeWidth={1.75} aria-hidden="true" /> : <Database size={14} strokeWidth={1.75} aria-hidden="true" />}{result.mode === "ai" ? "AI analysis" : context.task === "data" ? "Local checks" : "Recorded evidence"}</span>}</span></div>
    {capabilities?.live_available && !running && <div className="analysis-rerun"><Button size="sm" variant="secondary" onClick={retry} aria-label="Rerun with AI" title="Rerun with AI"><RotateCcw size={14} strokeWidth={1.75} aria-hidden="true" /></Button></div>}
    {capabilities && !thinking && ((capabilities.unlock_available && !capabilities.unlocked) || (consent && !consent.allowed)) && <div className="analysis-ai-setup" role="group" aria-label="AI analysis access">
      {capabilities.unlock_available && !capabilities.unlocked && <form onSubmit={event => { event.preventDefault(); void act(async () => { await unlock(code); setCode(""); }); }}><label htmlFor="presenter-code">Presenter access code</label><input id="presenter-code" type="password" autoComplete="off" value={code} onChange={event => setCode(event.target.value)} required maxLength={200} /><Button size="sm" variant="secondary" type="submit" loading={busy}>Unlock live AI</Button></form>}
      {consent && !consent.allowed && <div className="analysis-consent"><h3>AI analysis for this {consentLabel}</h3><p>{consent.disclosure}</p><Button size="sm" variant="secondary" loading={busy} onClick={() => void act(async () => { await setConsent(true); retry(); })}>Enable AI analysis</Button></div>}
    </div>}
    </div>
    {(thinking || (result && stages.length > 0)) ? <AssistantThinkingState stages={stages} working={thinking} label={context.task === "brief" ? "Preparing review brief" : "Analyzing evidence"} doneLabel={`${context.task === "brief" ? "Prepared brief" : "Analyzed evidence"}${elapsed > 0 ? ` in ${elapsed}s` : ""}`} /> : null}
    {!thinking && <>
    {!result && record && <section className="analysis-progress" aria-label="Analysis status"><div className="analysis-progress-head"><strong>{record.status === "cancelled" ? "Analysis cancelled" : record.status === "interrupted" ? "Analysis interrupted" : "Analysis stopped"}</strong><span>{elapsed}s</span></div><Button variant="secondary" size="sm" onClick={retry}>Try again</Button></section>}
    {(error || record?.error || operationError) && <div className="analysis-error" role="alert"><CircleAlert size={16} /><p>{operationError || error || record?.error}</p>{error && <Button size="sm" variant="ghost" onClick={retry}>Try again</Button>}</div>}
    {!running && !record && !error && <Button variant="secondary" onClick={retry}>Run analysis</Button>}
    {!running && result?.fallback_reason && capabilities?.live_available && <div className="analysis-fallback" role="status"><CircleAlert size={16} aria-hidden="true" /><p>{result.fallback_reason}</p></div>}
    {result && <>
      <span className="sr-only" role="status">{context.task === "brief" ? "Review brief ready." : "Analysis complete."}</span>
      {context.task === "brief" && record ? <div className="review-workspace">
        <section className="analysis-brief" aria-label="Review draft">
          <div className="review-editor-heading"><div><FileText size={16} aria-hidden="true" /><h3>Review draft</h3></div><span className="review-draft-status">{saved && <Check size={13} aria-hidden="true" />}{saved ? "Saved" : "Draft"}</span></div>
          <label className="sr-only" htmlFor="analysis-review">Edit before saving</label>
          <textarea id="analysis-review" value={draft} maxLength={12000} rows={14} onChange={event => { edited.current = true; setDraft(event.target.value); setSaved(false); editBrief(event.target.value); }} />
          <div className="review-save-row">
            <p className="note" role="status">{saved ? "Saved as an engineer review draft." : "Save before exporting."}</p>
            <div className="analysis-brief-actions"><Button variant="secondary" loading={busy} disabled={!draft.trim() || saved} onClick={() => void act(async () => { await saveBrief(draft); setSaved(true); })}>{saved ? "Saved" : "Save draft"}</Button><Button variant="secondary" disabled={!saved || busy} loading={busy} onClick={() => void act(() => assistant.export(record.id))}><Download size={16} aria-hidden="true" />Export brief</Button></div>
          </div>
        </section>
        <details className="review-reference analysis-disclosure disclosure-plain"><summary>Supporting evidence</summary><div className="analysis-disclosure-content"><EvidenceDetails result={result} /><ResultLimits result={result} /></div></details>
      </div> : <ResultContent result={result} follow={follow} candidates={candidates} task={context.task} reused={Boolean(record?.reused)} />}
      {!running && record?.status === "completed" && context.task === "data" && result.suggested_mapping && <section className="analysis-mapping" aria-label="Suggested mapping"><h3>Suggested column roles</h3><dl><div><dt>Equipment</dt><dd>{result.suggested_mapping.equipment_id}</dd></div><div><dt>Cycle</dt><dd>{result.suggested_mapping.cycle_index}</dd></div><div><dt>Failure</dt><dd>{result.suggested_mapping.failure_cycle || "Requires your confirmation"}</dd></div><div><dt>Sensors</dt><dd>{result.suggested_mapping.sensors.join(", ")}</dd></div></dl><Button variant="secondary" disabled={busy} onClick={applyMapping}>Use draft mapping</Button><p className="note">Review the roles before confirming.</p></section>}
      {!running && record?.status === "completed" && context.task !== "data" && context.task !== "brief" && enabled("brief") && <div className="analysis-brief-actions"><Button size="sm" variant="secondary" loading={busy} onClick={() => void act(prepareReview)}><FileText size={15} aria-hidden="true" />Add to review brief</Button></div>}
      <AnalysisAudit result={result} showFallback={!capabilities?.live_available} />
    </>}
    </>}
  </div>;
}

const COMPARED: [string, string][] = [["qualifies", "Meets limits"], ["required_passed", "Required cases passed"], ["clean_detection", "Healthy: warned in time"], ["clean_early_alarm_burden", "Healthy: early alarm time"], ["worst_burden_required", "Worst fault early alarm"], ["mean_detection_required", "Average fault detection"]];
function ComparisonTable({ result, candidates }: { result: AnalysisResult; candidates: string[] }) {
  const value = (candidate: string, metric: string) => result.sources.find(source => source.candidate === candidate && source.metric === metric);
  const rows = COMPARED.filter(([metric]) => candidates.every(candidate => value(candidate, metric)));
  return <div className="table-scroll analysis-compare"><table><caption className="sr-only">Selected model comparison</caption><thead><tr><th scope="col">Measure</th>{candidates.map(candidate => <th scope="col" className="num" key={candidate}>{candidate.split("/")[1]}</th>)}</tr></thead>
    <tbody>{rows.map(([metric, label]) => <tr key={metric}><th scope="row">{label}</th>{candidates.map(candidate => <td className="num" key={candidate}>{value(candidate, metric)!.display}{metric === "required_passed" && value(candidate, "required_scenarios") ? ` / ${value(candidate, "required_scenarios")!.display}` : ""}</td>)}</tr>)}</tbody></table></div>;
}

function ResultContent({ result, follow, candidates, task, reused }: { result: AnalysisResult; follow: () => void; candidates: string[]; task: string; reused: boolean }) {
  const hasAssessment = Boolean(result.assessment?.length);
  const inspected = result.findings.find(finding => finding.id.startsWith("inspected-"));
  const dataIssue = task === "data" && hasAssessment ? result.findings.find(finding => finding.tone === "danger" || finding.tone === "warning") : undefined;
  const warning = task === "warning" ? result.findings.find(finding => finding.source_ids.some(id => result.sources.some(source => source.id === id && source.metric === "alert_active"))) : undefined;
  const inspectedSources = inspected ? sourcesFor(result, inspected.source_ids) : [];
  const inspectedScenario = inspectedSources.find(source => source.scenario_id)?.scenario_id ?? undefined;
  const primary = candidates[0] ?? "";
  return <div className="analysis-layout">
    <section className="analysis-findings" aria-label="Finding">
      {task === "investigate" && <Verdict result={result} candidate={primary} examined={inspectedScenario} />}
      {hasAssessment ? <Assessment result={result} reused={reused} /> : <><h3>{task === "compare" ? "Comparison" : task === "data" ? "Data checks" : "Conclusion"}</h3>{result.findings[0] ? <Finding finding={result.findings[0]} /> : <p>{result.summary}</p>}</>}
      {task === "investigate" && inspected && inspectedScenario !== weakestDetection(result, primary)?.scenario_id && <ExaminedCase finding={inspected} sources={inspectedSources} />}
      {dataIssue && <section className="analysis-case" aria-label="Data issue"><Finding finding={dataIssue} /></section>}
      {warning && <section className="analysis-case" aria-label="Warning timing"><h3>Warning timing</h3><p>{warning.detail}</p></section>}
      {task === "compare" && candidates.length === 2 && <ComparisonTable result={result} candidates={candidates} />}
      {result.interpretation && <Interpretation result={result} />}
    </section>
    <NextChecks result={result} follow={follow} />
    <div className="analysis-more">
      <details className="analysis-evidence analysis-disclosure disclosure-plain"><summary>Evidence and test details</summary><div className="analysis-disclosure-content"><EvidenceDetails result={result} /></div></details>
      <ResultLimits result={result} />
    </div>
    {task !== "data" && <p className="analysis-boundary">Test evidence, not deployment approval.</p>}
  </div>;
}

function sourcesFor(result: AnalysisResult, ids: string[]) {
  return ids.map(id => result.sources.find(source => source.id === id)).filter((source): source is EvidenceReference => Boolean(source));
}
const numeric = (source?: EvidenceReference) => source && source.value !== "unavailable" && Number.isFinite(Number(source.value)) ? Number(source.value) : undefined;
const scenarioName = (source: EvidenceReference) => source.context.split(" · ")[2] ?? "Recorded fault case";
function extreme(sources: EvidenceReference[], metric: string, direction: 1 | -1) {
  return sources.filter(source => source.metric === metric && source.scenario_id && source.scenario_id !== "clean" && numeric(source) !== undefined)
    .sort((first, second) => direction * (numeric(first)! - numeric(second)!))[0];
}
function weakestDetection(result: AnalysisResult, candidate: string) {
  return extreme(result.sources.filter(source => source.candidate === candidate), "detection_fraction", 1);
}

/** Deterministic outcome from recorded evidence; shown before and independently of the AI text. */
function Verdict({ result, candidate, examined }: { result: AnalysisResult; candidate: string; examined?: string }) {
  const own = result.sources.filter(source => source.candidate === candidate);
  const overall = (metric: string) => own.find(source => source.metric === metric && !source.scenario_id);
  const qualifies = overall("qualifies");
  if (!qualifies) return null;
  const passes = qualifies.value.toLowerCase() === "true";
  const passed = overall("required_passed");
  const total = overall("required_scenarios");
  const weakest = weakestDetection(result, candidate);
  const burden = extreme(own, "early_alarm_burden", -1);
  const minimum = own.find(source => source.metric === "min_detection_fraction");
  const maximum = own.find(source => source.metric === "max_early_alarm_burden");
  const examinedWeakest = weakest && weakest.scenario_id === examined
    ? own.find(source => source.scenario_id === examined && source.metric === "detected") : undefined;
  const examinedTotal = examinedWeakest && own.find(source => source.scenario_id === examined && source.metric === "engines");
  return <section className={`analysis-verdict ${passes ? "ok" : "bad"}`} aria-label="Verdict">
    <div className="analysis-verdict-head">
      <span className="analysis-verdict-badge">{passes ? <Check size={14} strokeWidth={2.6} aria-hidden="true" /> : <X size={14} strokeWidth={2.6} aria-hidden="true" />}{passes ? "Meets test limits" : "Does not meet test limits"}</span>
      {passed && total && <span className="analysis-verdict-count">{passed.display} / {total.display} required fault cases passed</span>}
    </div>
    {(weakest || burden) && <dl className="analysis-metrics">
      {weakest && <Metric label="Weakest fault detection" value={weakest.display} limit={minimum && `min ${minimum.display}`} failing={minimum ? numeric(weakest)! < numeric(minimum)! : undefined} note={scenarioName(weakest)} tag={examinedWeakest ? `Examined · ${examinedWeakest.display}${examinedTotal ? ` / ${examinedTotal.display}` : ""} histories` : undefined} />}
      {burden && <Metric label="Highest early alarm time" value={burden.display} limit={maximum && `max ${maximum.display}`} failing={maximum ? numeric(burden)! > numeric(maximum)! : undefined} note={scenarioName(burden)} />}
    </dl>}
  </section>;
}
function Metric({ label, value, limit, failing, note, tag }: { label: string; value: string; limit?: string; failing?: boolean; note?: string; tag?: string }) {
  return <div className={`analysis-metric${failing === undefined ? "" : failing ? " bad" : " ok"}`}>
    <dt>{label}</dt>
    <dd><strong>{value}</strong>{limit && <span className="analysis-metric-limit">{limit}</span>}</dd>
    {note && <dd className="analysis-metric-note" title={note}>{note}</dd>}
    {tag && <dd className="analysis-metric-tag"><ScanLine size={12} aria-hidden="true" />{tag}</dd>}
  </div>;
}
function ExaminedCase({ finding, sources }: { finding: AnalysisFinding; sources: EvidenceReference[] }) {
  const get = (metric: string) => sources.find(source => source.metric === metric);
  const detected = get("detected"), engines = get("engines"), burden = get("early_alarm_burden");
  const name = sources.find(source => source.scenario_id) ? scenarioName(sources.find(source => source.scenario_id)!) : undefined;
  return <section className="analysis-case" aria-label="Inspected case">
    <h3>Fault examined</h3>
    {name && detected && engines ? <p className="analysis-case-line"><span className="analysis-case-name">{name}</span><span>{detected.display} / {engines.display} warned in time{burden ? ` · ${burden.display} early alarm time` : ""}</span></p> : <p>{finding.detail}</p>}
  </section>;
}
function Assessment({ result, reused }: { result: AnalysisResult; reused: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  const assessment = result.assessment ?? [];
  // Several inspected cases can support the same claim. Say it once and retain every citation.
  const claims = assessment.filter((claim, index, all) => all.findIndex(other => other.text === claim.text) === index)
    .map(claim => ({ ...claim, source_ids: [...new Set(assessment.filter(other => other.text === claim.text).flatMap(other => other.source_ids))] }))
    .sort((first, second) => Number(!first.id.startsWith("limits-")) - Number(!second.id.startsWith("limits-")));
  const wordCount = claims.reduce((count, claim) => count + streamWords(claim.text).length, 0);
  const visible = useStreamingReveal(wordCount, 320, reused);
  const done = visible === wordCount;
  let offset = 0;
  if (!assessment.length) return null;
  return <section className="analysis-assessment" aria-label="Assessment" aria-busy={!done}><h3>Assessment<span>Each claim cites recorded evidence</span></h3>{claims.map((claim, index) => {
    const sources = claim.source_ids.map(id => result.sources.find(source => source.id === id)).filter((source): source is EvidenceReference => Boolean(source));
    const words = streamWords(claim.text).length;
    const visibleWords = visible - offset;
    offset += words;
    const streaming = visibleWords > 0 && visibleWords < words;
    return <article key={claim.id} className={index === 0 ? "assessment-conclusion" : undefined}><p><StreamingText text={claim.text} visibleWords={visibleWords} caret={streaming} />{sources.length > 0 && <EvidenceCitation number={index + 1} expanded={selected === claim.id} controls={`claim-${claim.id}`} disabled={visibleWords < words} onClick={() => setSelected(selected === claim.id ? null : claim.id)} />}</p>
      {selected === claim.id && <div id={`claim-${claim.id}`} className="assessment-proof" role="region" aria-label={`Evidence for finding ${index + 1}`}><EvidenceSources sources={sources} cards /></div>}
    </article>;
  })}</section>;
}
function Interpretation({ result }: { result: AnalysisResult }) {
  return <details className="analysis-interpretation"><summary>AI interpretation</summary><p className="note">Verify against the evidence.</p><p>{result.interpretation}</p></details>;
}
function EvidenceSources({ sources, cards = false, grouped = false }: { sources: EvidenceReference[]; cards?: boolean; grouped?: boolean }) {
  // Historical and inspected references can describe the same measurement.
  const unique = sources.filter((source, index) => sources.findIndex(other => other.candidate === source.candidate && other.partition === source.partition && other.scenario_id === source.scenario_id && other.equipment_id === source.equipment_id && other.cycle === source.cycle && other.metric === source.metric && other.value === source.value && other.unit === source.unit && other.context === source.context) === index);
  if ((cards || grouped) && unique.length) return <EvidenceContextCards sources={unique} variant={grouped ? "rows" : "cards"} />;
  return <dl className="analysis-source-list">{unique.length ? unique.map(source => <div className="analysis-source" key={source.id}><dt>{source.label}<small>{source.context}</small></dt><dd>{source.display}</dd></div>) : <div><dt className="note">No source references available.</dt></div>}</dl>;
}
function EvidenceDetails({ result }: { result: AnalysisResult }) {
  return <><EvidenceSources sources={result.sources} grouped />{result.findings.length > 0 && <details className="analysis-supporting disclosure-plain"><summary>Detailed findings</summary>{result.findings.map(finding => <Finding key={finding.id} finding={finding} />)}</details>}</>;
}
function NextChecks({ result, follow }: { result: AnalysisResult; follow: () => void }) {
  const action = result.actions[0];
  const detail = action?.id.startsWith("inspect-") ? "Review late and missed warnings in this case before retesting." : action?.detail;
  return action ? <section className="analysis-next" aria-label="Next check"><div><h3>Next check</h3><p>{detail}</p></div><Link className="button primary" to={action.href} onClick={follow}>{action.label}<ArrowRight size={14} aria-hidden="true" /></Link></section> : null;
}
function ResultLimits({ result }: { result: AnalysisResult }) {
  return result.limitations.length ? <details className="analysis-limits analysis-disclosure disclosure-plain"><summary>What this does not establish</summary><div className="analysis-disclosure-content"><ul>{result.limitations.map(item => <li key={item}>{item}</li>)}</ul></div></details> : null;
}

function AnalysisAudit({ result, showFallback }: { result: AnalysisResult; showFallback: boolean }) {
  const steps: { name: string; label: string; count: number }[] = [];
  for (const call of result.investigation ?? []) {
    const previous = steps[steps.length - 1];
    if (previous?.name === call.name && previous.label === call.label) previous.count += 1;
    else steps.push({ name: call.name, label: call.label, count: 1 });
  }
  return <details className="analysis-audit analysis-disclosure disclosure-plain"><summary>Analysis record</summary><div className="analysis-disclosure-content">
    {steps.length > 0 && <ol className="investigation-log">{steps.map((step, index) => <li key={`${index}-${step.name}`}><span>{step.label}</span>{step.count > 1 && <span className="investigation-repeat" aria-label={`Repeated ${step.count} times`}>× {step.count}</span>}</li>)}</ol>}
    <p className="analysis-verification">{result.verification}</p>
    <dl className="analysis-record-metadata"><div><dt>Model</dt><dd>{result.model ?? "Recorded evidence"}</dd></div>{result.prompt_version && <div><dt>Prompt</dt><dd>{result.prompt_version}</dd></div>}<div><dt>Evidence ID</dt><dd><code>{result.evidence_digest}</code></dd></div></dl>
    {result.fallback_reason && showFallback && <p className="analysis-record-fallback">{result.fallback_reason}</p>}
  </div></details>;
}
function Finding({ finding }: { finding: AnalysisFinding }) {
  return <article className={`analysis-insight ${finding.tone ?? "neutral"}`}><h4>{finding.tone === "success" ? <Check size={15} /> : finding.tone === "danger" || finding.tone === "warning" ? <CircleAlert size={15} /> : <ScanLine size={15} />}{finding.title}</h4><p>{finding.detail}</p></article>;
}
