import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Bot, FlaskConical, Play } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import SegmentedControl from "@/components/arc/segmented-control/segmented-control";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/arc/tabs/tabs";
import { investigations } from "../api/client";
import type { Finding, InvestigationView, ProposalDetail } from "../api/types";
import { Badge, Button, Callout, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { percent } from "../format";
import { caseTitle, describeCase, effectText, errorText, faultKinds, findingTones, histories, requestId, stops } from "../components/investigations/cases";
import { Disclosure } from "../components/investigations/Disclosure";
import { ExportMenu } from "../components/investigations/ExportMenu";
import { WarningComparison } from "../components/investigations/WarningComparison";
import { RollingNumber } from "../components/cult/RollingNumber";
import styles from "./investigations.module.css";

type Act = (label: string, action: () => Promise<unknown>) => Promise<boolean>;
type Tab = "results" | "run" | "fix" | "activity";

interface ControllerCall { sequence: number; status: string; proposalId?: string | null; error?: string | null; feedback?: string | null;
  reservedCompletionTokens?: number; usage?: { completion_tokens?: number } | null; elapsedSeconds?: number | null }

const controllerCalls = (data: InvestigationView) => ((data.controller as { calls?: ControllerCall[] } | null)?.calls) ?? [];

export function InvestigationDetail() {
  const { investigationId = "" } = useParams();
  const view = useApi(() => investigations.get(investigationId), [investigationId]);
  // Keep the last view on screen while polling, so inputs and messages survive each refresh.
  const [last, setLast] = useState<InvestigationView | null>(null);
  useEffect(() => { if (view.data) setLast(view.data); }, [view.data]);
  const data = view.data ?? (last?.id === investigationId ? last : null);
  const active = Boolean(data?.active);
  const { reload } = view;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(reload, 2000);
    return () => clearInterval(timer);
  }, [active, reload]);
  return <StateBlock loading={!data && view.loading} error={data ? null : view.error}>
    {data && view.error && <Callout tone="warn" title="Showing the last saved results"><p>The latest status could not be loaded. Your saved results are still available.</p><Button variant="secondary" onClick={reload}>Refresh investigation status</Button></Callout>}
    {data && <Detail key={data.id} data={data} reload={reload} />}
  </StateBlock>;
}

function Detail({ data, reload }: { data: InvestigationView; reload: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [tab, setTab] = useState<Tab>(data.experimentsUsed || data.active ? "results" : "run");
  const pending = useRef(false);
  const lastEvent = data.events.at(-1);
  const failed = lastEvent?.kind.startsWith("failed:") ? lastEvent : null;

  async function act(label: string, action: () => Promise<unknown>) {
    if (pending.current) return false;
    pending.current = true;
    setBusy(label); setError("");
    try { await action(); reload(); return true; } catch (failure) { setError(errorText(failure)); return false; } finally { setBusy(""); pending.current = false; }
  }

  async function start(label: string, action: () => Promise<unknown>) {
    const started = await act(label, action);
    if (started) setTab("results");
    return started;
  }

  async function exportEvidence(kind: "export" | "public") {
    await act(kind, async () => {
      const url = kind === "public" ? investigations.publicExportUrl(data.id) : investigations.exportUrl(data.id);
      const response = await fetch(url, { headers: { "X-Sidekick-Request": "1" } });
      if (!response.ok) throw new Error(`Export failed (${response.status}). Try again.`);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([JSON.stringify(await response.json(), null, 2)], { type: "application/json" }));
      link.download = `sidekick-investigation-${data.id.slice(0, 8)}${kind === "public" ? "-public" : ""}.json`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
  }

  const status = data.active ? ["Running " + data.active, "info"] as const : data.stopReason ? stops[data.stopReason] ?? [data.stopReason, "neutral"] as const : ["Not started", "neutral"] as const;
  const failures = data.findings.filter(item => item.attempt_id && item.status === "measured_failure").length;
  return <>
    <header className={`page-head ${styles.detailHead}`}>
      <Link className={styles.backLink} to="/investigations"><ArrowLeft size={14} aria-hidden="true" />All investigations</Link>
      <div className={styles.titleRow}><h1>{data.objective}</h1>
        <div className={styles.headActions}><Badge tone={status[1]}>{status[0]}</Badge><ExportMenu busy={busy === "export" || busy === "public"} onExport={exportEvidence} /></div></div>
    </header>
    <dl className={styles.summary}>
      <div><dt>Fault tests used</dt><dd><RollingNumber value={data.experimentsUsed} /><span className={styles.outOf}> / {data.maxExperiments}</span>
        <span className={styles.budgetTrack} aria-hidden="true"><span style={{ width: `${Math.min(100, data.experimentsUsed / data.maxExperiments * 100)}%` }} /></span></dd></div>
      <div><dt>Measured failures</dt><dd><RollingNumber value={data.discoveries} /></dd></div>
      <div><dt>Distinct failure patterns</dt><dd><RollingNumber value={data.discoveryFamilies.length} /></dd></div>
    </dl>
    {data.active && <Callout title="Running"><div className={styles.inline}><p>Results appear as each test finishes. Cancelling stops at the next safe point.</p>
      <Button variant="danger" onClick={() => act("cancel", () => investigations.cancel(data.id))} loading={busy === "cancel"}>Cancel</Button></div></Callout>}
    {failed && <Callout tone="fault" title="The last operation failed">{failed.detail}</Callout>}
    {lastEvent?.kind === "interrupted" && <Callout tone="warn" title="Interrupted">{lastEvent.detail} Start again to recover within the saved limits.</Callout>}
    {data.state.cancel_requested && !data.active && <Callout tone="warn" title="Cancellation is saved"><div className={styles.inline}><p>Resume before starting more work.</p>
      <Button onClick={() => act("resume", () => investigations.resume(data.id))} loading={busy === "resume"}>Resume</Button></div></Callout>}
    {/* The page transform would pin a fixed alert to the page instead of the screen. */}
    {error && createPortal(<div role="alert" className={`${styles.error} ${styles.toast}`}><span>{error}</span>
      <Button variant="ghost" onClick={() => setError("")}>Dismiss</Button></div>, document.body)}
    <Tabs className={styles.tabs} value={tab} onValueChange={value => setTab(value as Tab)}>
      <TabsList aria-label="Investigation sections">
        <TabsTrigger value="results">Results{failures > 0 && <span className={styles.count}>{failures}</span>}</TabsTrigger>
        <TabsTrigger value="run">Run tests</TabsTrigger><TabsTrigger value="fix">Compare a fix</TabsTrigger><TabsTrigger value="activity">Activity</TabsTrigger>
      </TabsList>
      <TabsContent value="results" forceMount hidden={tab !== "results"}><Results data={data} busy={busy} act={act} onRun={() => setTab("run")} /></TabsContent>
      <TabsContent value="run" forceMount hidden={tab !== "run"}><Controls data={data} busy={busy} act={start} /></TabsContent>
      <TabsContent value="fix" forceMount hidden={tab !== "fix"}><Remedies data={data} busy={busy} act={act} onRun={() => setTab("run")} /></TabsContent>
      <TabsContent value="activity" forceMount hidden={tab !== "activity"}><Activity data={data} /></TabsContent>
    </Tabs>
  </>;
}

function Results({ data, busy, act, onRun }: { data: InvestigationView; busy: string; act: Act; onRun: () => void }) {
  const tested = data.findings.filter(item => item.attempt_id);
  const flagged = tested.filter(item => item.status !== "no_measured_failure").sort((a, b) => Number(b.status === "measured_failure") - Number(a.status === "measured_failure"));
  const passed = tested.filter(item => item.status === "no_measured_failure");
  if (!data.criterion) return <p className={styles.empty}>This investigation has no finding criterion, so results are not classified.</p>;
  if (!tested.length) return <div className={styles.empty}><FlaskConical size={23} aria-hidden="true" /><h3>No results yet</h3><p>Finished fault tests appear here.</p>
    {!data.active && <Button variant="primary" onClick={onRun}>Choose how to run tests</Button>}</div>;
  return <div className={styles.results}>
    <h2 className="sr-only">Findings</h2>
    {flagged.map(finding => <FindingCard key={finding.attempt_id} finding={finding} data={data} busy={busy} act={act} />)}
    {passed.length > 0 && <section className={styles.passed} aria-label="Tests without a measured failure">
      <h3>{passed.length} {passed.length === 1 ? "test" : "tests"} without a measured failure</h3>
      {passed.map(finding => <PassedRow key={finding.attempt_id} finding={finding} data={data} busy={busy} act={act} />)}
    </section>}
    {data.reductions.length > 0 && <Reductions reductions={data.reductions} />}
  </div>;
}

function Meta({ finding, data }: { finding: Finding; data: InvestigationView }) {
  const [label, tone] = findingTones[finding.status];
  const chosen = controllerCalls(data).some(call => call.proposalId === finding.proposal_id);
  const partial = (finding.evaluated_histories ?? 0) < (finding.expected_histories ?? 0);
  return <div className={styles.meta}><Badge tone={tone}>{label}</Badge>{partial && finding.status !== "execution_error" && <Badge tone="warn">Partial coverage</Badge>}
    <span>{chosen ? <><Bot size={14} aria-hidden="true" />Chosen by Nemotron</> : "Supplied case"}</span>
    {finding.status !== "execution_error" && <span>{finding.evaluated_histories ?? 0} of {finding.expected_histories ?? 0} histories</span>}</div>;
}

function FindingCard({ finding, data, busy, act }: { finding: Finding; data: InvestigationView; busy: string; act: Act }) {
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  const unscored = finding.status === "not_applicable" || finding.status === "inconclusive";
  return <article className={styles.finding} aria-label={`${findingTones[finding.status][0]}: ${finding.family ?? "case"}`} data-status={finding.status}>
    <header><h3>{caseTitle(proposal?.scenario)}</h3><Meta finding={finding} data={data} /></header>
    {finding.status === "execution_error" ? <p className={styles.reason}>{finding.reasons?.[0]}</p> : <>
      <Measured finding={finding} />
      {unscored && <p><strong>Why this was not scored as a finding:</strong></p>}
      {finding.reasons?.map(reason => <p key={reason} className={styles.reason}>{reason}</p>)}
      <Tools finding={finding} data={data} busy={busy} act={act} />
    </>}
  </article>;
}

function PassedRow({ finding, data, busy, act }: { finding: Finding; data: InvestigationView; busy: string; act: Act }) {
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  return <article className={styles.passedRow} aria-label={`${findingTones[finding.status][0]}: ${finding.family ?? "case"}`}>
    <Disclosure title={caseTitle(proposal?.scenario)} description={`Useful warnings ${percent(finding.clean_detection)} → ${percent(finding.faulted_detection)} · ${finding.evaluated_histories ?? 0} of ${finding.expected_histories ?? 0} histories`}>
      <Meta finding={finding} data={data} /><Measured finding={finding} /><Tools finding={finding} data={data} busy={busy} act={act} />
    </Disclosure>
  </article>;
}

function Measured({ finding }: { finding: Finding }) {
  return <>
    <div className={styles.comparisonGrid}><WarningComparison before={finding.clean_detection} after={finding.faulted_detection} />
      <WarningComparison label="Early alarm burden" before={finding.clean_burden} after={finding.faulted_burden} lowerIsBetter /></div>
    {(finding.effects?.length ?? 0) > 0 && <p className={styles.effects}>{finding.effects?.map(effect => effectText(effect.kind, effect.histories.length)).join(" · ")}</p>}
  </>;
}

function Tools({ finding, data, busy, act }: { finding: Finding; data: InvestigationView; busy: string; act: Act }) {
  const [replay, setReplay] = useState("");
  const [open, setOpen] = useState<"" | "details" | "research">("");
  const attempt = finding.attempt_id ?? "";
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  const report = data.research?.find(item => item.attempt === attempt);
  const locked = Boolean(data.active) || Boolean(busy) || data.state.cancel_requested;
  const toggle = (panel: "details" | "research") => setOpen(open === panel ? "" : panel);
  return <>
    <div className={styles.actions}>
      {finding.status === "measured_failure" && <Button variant="primary" disabled={locked} loading={busy === `reduce-${attempt}`}
        onClick={() => act(`reduce-${attempt}`, () => investigations.reduce(data.id, { requestId: requestId(), attempt, maxExperiments: 16 }))}>Reduce</Button>}
      <Button variant="secondary" disabled={Boolean(busy)} loading={busy === `replay-${attempt}`} onClick={() => act(`replay-${attempt}`, async () => {
        const check = await investigations.replay(data.id, attempt);
        setReplay(check.matches ? "Replay reproduced this result exactly." : "Replay did not reproduce this result.");
      })}>Replay</Button>
      {!report && <Button variant="ghost" onClick={() => toggle("research")} aria-expanded={open === "research"}>Research this fault</Button>}
      <Button variant="ghost" onClick={() => toggle("details")} aria-expanded={open === "details"}>Details</Button>
      {replay && <span role="status" className={styles.footnote}>{replay}</span>}
    </div>
    {open === "details" && <div className={styles.toolPanel}>
      <p className={styles.footnote}>{describeCase(proposal?.scenario)}</p>
      {(finding.support?.length ?? 0) > 0 && <details><summary>{histories(finding.support?.length ?? 0)} with recorded changes</summary>
        <div className="table-scroll"><table><thead><tr><th>History</th><th>Clean</th><th>Faulted</th><th className="num">Lead</th></tr></thead>
          <tbody>{finding.support?.map(row => <tr key={row.equipment_id}><td>{row.equipment_id}</td><td>{row.clean}</td><td>{row.faulted}</td>
            <td className="num">{row.clean_lead ?? "—"} → {row.faulted_lead ?? "—"}</td></tr>)}</tbody></table></div></details>}
      {(finding.assumptions?.length ?? 0) > 0 && <details><summary>Profile assumptions</summary><ul>{finding.assumptions?.map(item => <li key={item}>{item}</li>)}</ul></details>}
    </div>}
    {report ? <ResearchReport report={report} /> : open === "research" && <ResearchConsent finding={finding} data={data} busy={busy} act={act} locked={locked} />}
  </>;
}

function ResearchConsent({ finding, data, busy, act, locked }: { finding: Finding; data: InvestigationView; busy: string; act: Act; locked: boolean }) {
  const [allow, setAllow] = useState(false);
  const attempt = finding.attempt_id ?? "";
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  const query = `industrial sensor ${faultKinds(proposal?.scenario)} readings troubleshooting manufacturer documentation predictive maintenance`;
  return <fieldset className={styles.toolPanel}><legend>Research this fault</legend>
    <p>One Tavily search for:</p><p className={styles.query}>{query}</p>
    <p className={styles.footnote}>Then one Nemotron request (at most 5,120 completion tokens) reads up to three excerpts with aliased aggregate results. No raw readings, sensor names, equipment IDs or your concern are sent. Workspace AI permission is required.</p>
    <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow Tavily search and Nemotron research for this fault</label>
    <div className={styles.actions}><Button disabled={!allow || locked} loading={busy === `research-${attempt}`}
      onClick={() => act(`research-${attempt}`, () => investigations.research(data.id, { requestId: requestId(), attempt, allowResearch: true }))}>Start fault research</Button></div>
  </fieldset>;
}

function ResearchReport({ report }: { report: NonNullable<InvestigationView["research"]>[number] }) {
  const sources = (ids: string[]) => (report.sources ?? []).filter(source => ids.includes(source.id)).map(source =>
    <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>);
  return <section className={styles.toolPanel} aria-label="Fault research">
    <div className={styles.meta}><strong>Fault research</strong><Badge tone={report.status === "completed" ? "info" : "neutral"}>{report.status.replace(/_/g, " ")}</Badge></div>
    {report.error && <p role="status">{report.error}</p>}
    {report.note && <>
      <p>{report.note.summary}</p><div className={styles.sources}>{sources(report.note.sourceIds)}</div>
      <ul className={styles.tests}>{report.note.tests.map((test, index) => <li key={index}><strong>{test.action}</strong><span>{test.reason}</span>
        <span className={styles.sources}>{sources(test.sourceIds)}</span></li>)}</ul>
      <details><summary>Saved source excerpts and search</summary><p>{report.query}</p>{(report.sources ?? []).map(source =>
        <div key={source.id}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a><p>{source.content}</p></div>)}</details>
    </>}
    <p className={styles.footnote}>External references, separate from measured findings. Sources do not validate the fault policy or prove a physical cause. {report.searchRequests} Tavily {report.searchRequests === 1 ? "search" : "searches"}, {report.modelRequests} Nemotron {report.modelRequests === 1 ? "request" : "requests"}, {report.reportedCompletionTokens ?? "unreported"} of {report.reservedCompletionTokens} reserved tokens.</p>
  </section>;
}

function Reductions({ reductions }: { reductions: Record<string, unknown>[] }) {
  return <section className={styles.reductions} aria-label="Simplified failures"><h3>Simplified failures</h3>
    {reductions.map(item => {
      const reduction = item as { id: string; status: string; experiments: number; claims: string[]; original: Record<string, unknown>; final: Record<string, unknown> | null; steps: unknown[] };
      const final = reduction.final ?? reduction.original;
      return <article key={reduction.id} className={styles.reduction}>
        <div className={styles.reductionPath}><div><span>Original</span><strong>{caseTitle(reduction.original)}</strong><p className={styles.footnote}>{describeCase(reduction.original)}</p></div>
          <ArrowRight size={18} aria-hidden="true" /><div><span>Simplified</span><strong>{caseTitle(final)}</strong><p className={styles.footnote}>{describeCase(final)}</p></div></div>
        <div className={styles.meta}><Badge tone={reduction.status === "complete" ? "ok" : "warn"}>{reduction.status.replace(/_/g, " ")}</Badge>
          <span>{reduction.experiments} additional tests · {reduction.steps.length} checked steps</span></div>
        <Disclosure title="Why this is a bounded result"><ul>{reduction.claims.map(claim => <li key={claim}>{claim}</li>)}</ul></Disclosure>
      </article>;
    })}
  </section>;
}

function Controls({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const [allow, setAllow] = useState(false);
  const [calls, setCalls] = useState("4");
  const [tokens, setTokens] = useState("32768");
  const controller = data.controller as { callsUsed?: number; reservedCompletionTokens?: number; reportedCompletionTokens?: number } | null;
  const locked = Boolean(data.active) || data.state.cancel_requested || Boolean(busy);
  const validCalls = Number.isInteger(Number(calls)) && Number(calls) >= 1 && Number(calls) <= 64;
  const validTokens = Number.isInteger(Number(tokens)) && Number(tokens) >= 1 && Number(tokens) <= 1000000;
  return <div className={styles.choices}>
    <section className={styles.choice} aria-labelledby="saved-checks">
      <h2 id="saved-checks"><Play size={16} aria-hidden="true" />Saved checks</h2>
      <p>Test the faults already saved in this investigation. Runs locally with no AI request.</p>
      <div className={styles.actions}><Button disabled={locked} loading={busy === "run"} onClick={() => act("run", () => investigations.start(data.id, { requestId: requestId(), mode: "run" }))}>Run saved proposals</Button></div>
    </section>
    <fieldset className={styles.choice}>
      <legend><Bot size={16} aria-hidden="true" />Nemotron search</legend>
      <p>Nemotron picks a sensor fault, reads the measured result and decides what to test next.</p>
      <div className={styles.fields}>
        <Input label="Provider calls" description="1 to 64 requests" type="number" min={1} max={64} value={calls} onChange={event => setCalls(event.target.value)} />
        <Input label="Completion token ceiling" description="Reserved, not billed usage" type="number" min={1} max={1000000} value={tokens} onChange={event => setTokens(event.target.value)} />
      </div>
      {(!validCalls || !validTokens) && <p role="alert" className={styles.error}>Use 1 to 64 provider calls and 1 to 1,000,000 completion tokens, as whole numbers.</p>}
      <Disclosure title="What is sent to Nebius"><p>Your concern, channel aliases with reviewed descriptions, fault bounds, baseline performance and aggregate matched results, on each call.</p>
        <p>Sensor names, raw readings, equipment IDs, fitted models and keys are excluded. Workspace AI permission is also required.</p></Disclosure>
      <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow sending this information to Nebius for this run</label>
      <div className={styles.actions}>
        <Button variant="primary" disabled={!allow || locked || !validCalls || !validTokens} loading={busy === "agent"} onClick={() => act("agent", () => investigations.start(data.id, { requestId: requestId(), mode: "agent", allowProvider: true, maxProviderCalls: Number(calls), maxCompletionTokens: Number(tokens) }))}>Start Nemotron search</Button>
        {controller && <span className={styles.footnote}>Calls used {controller.callsUsed ?? 0}; reserved {controller.reservedCompletionTokens ?? 0} tokens; reported {controller.reportedCompletionTokens ?? 0}.</span>}
      </div>
    </fieldset>
  </div>;
}

interface RemedyReport { id: string; kind: string; threshold: number | null; improved: number; degraded: number; stillFailing?: number; meetsCriteria: boolean;
  clean: { original: { detection: number; alarmBurden: number | null }; remedy: { detection: number; alarmBurden: number | null } }; note: string }

function Remedies({ data, busy, act, onRun }: { data: InvestigationView; busy: string; act: Act; onRun: () => void }) {
  const [kind, setKind] = useState<"threshold" | "augmented">("threshold");
  const [threshold, setThreshold] = useState("0.5");
  const [approve, setApprove] = useState(false);
  const ready = data.discoveries > 0 || data.reductions.length > 0;
  const reports = useMemo(() => data.remedies as unknown as RemedyReport[], [data.remedies]);
  const validThreshold = threshold.trim() !== "" && Number.isFinite(Number(threshold)) && Number(threshold) >= 0 && Number(threshold) <= 1;
  if (!ready) return <div className={styles.empty}><FlaskConical size={23} aria-hidden="true" /><h3>No failure to fix yet</h3>
    <p>Once a test finds a measured failure, compare a fix here and see what it costs elsewhere.</p>{!data.active && <Button onClick={onRun}>Run tests</Button>}</div>;
  return <div className={styles.results}>
    <form className={styles.fixForm} onSubmit={event => {
      event.preventDefault();
      if (kind === "threshold" && !validThreshold) return;
      void act("remedy", () => investigations.remedy(data.id, { requestId: requestId(), kind, threshold: kind === "threshold" ? Number(threshold) : null, approveTraining: approve }));
    }}>
      <SegmentedControl label="Remedy" value={kind} onValueChange={value => setKind(value as "threshold" | "augmented")} options={[{ value: "threshold", label: "Warning threshold" }, { value: "augmented", label: "Augmented retraining" }]} />
      {kind === "threshold" ? <Input label="Threshold" required type="number" min={0} max={1} step="any" value={threshold} onChange={event => setThreshold(event.target.value)} />
        : <label className={styles.check}><input type="checkbox" checked={approve} onChange={event => setApprove(event.target.checked)} />Approve development-only retraining</label>}
      <Button type="submit" variant="primary" disabled={Boolean(data.active) || Boolean(busy) || data.state.cancel_requested || (kind === "augmented" ? !approve : !validThreshold)} loading={busy === "remedy"}>Compare remedy</Button>
      <p className={styles.footnote}>A lower threshold recovers warnings but raises early alarms. Each comparison rechecks discovered failures and previously passing cases; your deployed model is not changed.</p>
    </form>
    {reports.map(report => <article key={report.id} className={styles.finding}>
      <header><h3>{report.kind === "threshold" ? `Threshold ${report.threshold}` : "Augmented retraining"}</h3>
        <div className={styles.meta}><Badge tone={report.meetsCriteria ? "ok" : "bad"}>{report.meetsCriteria ? "Comparison criteria met" : "Comparison criteria not met"}</Badge></div></header>
      <dl className={styles.tally}>
        <div data-tone="ok"><dt>Improved</dt><dd>{report.improved}</dd></div><div data-tone={report.degraded ? "bad" : undefined}><dt>Degraded</dt><dd>{report.degraded}</dd></div>
        <div data-tone={report.stillFailing ? "warn" : undefined}><dt>Still failing</dt><dd>{report.stillFailing ?? "—"}</dd></div>
      </dl>
      <div className={styles.comparisonGrid}><WarningComparison before={report.clean.original.detection} after={report.clean.remedy.detection} beforeLabel="Original model" afterLabel="With proposed fix" label="Warnings without sensor faults" />
        <WarningComparison before={report.clean.original.alarmBurden} after={report.clean.remedy.alarmBurden} beforeLabel="Original model" afterLabel="With proposed fix" label="Early alarm burden" lowerIsBetter /></div>
      <p className={styles.footnote}>{report.note}</p>
    </article>)}
  </div>;
}

const eventLabels: Record<string, string> = { created: "Created", cancel_requested: "Cancellation requested", resumed: "Resumed", interrupted: "Interrupted" };
const operations: Record<string, string> = { run: "saved fault tests", agent: "Nemotron search", reduce: "fault simplification", remedy: "fix comparison", research: "fault research" };

function Activity({ data }: { data: InvestigationView }) {
  const calls = controllerCalls(data);
  const rejected = data.proposals.filter(item => item.status === "rejected").length;
  return <div className={styles.results}>
    <section aria-labelledby="timeline"><h2 id="timeline" className={styles.sectionTitle}>Timeline</h2>
      <ol className={styles.timeline}>
        {[...data.events].reverse().map(event => {
          const [kind, operation] = event.kind.split(":");
          const text = operation ? `${kind === "started" ? "Started" : kind === "finished" ? "Finished" : "Failed"} ${operations[operation] ?? operation}` : eventLabels[event.kind] ?? event.kind;
          return <li key={event.sequence}><time dateTime={new Date(event.at * 1000).toISOString()}>{new Date(event.at * 1000).toLocaleTimeString()}</time>
            <span>{text}{event.detail ? `: ${stops[event.detail]?.[0] ?? event.detail}` : ""}</span></li>;
        })}
      </ol></section>
    {calls.length > 0 && <section aria-labelledby="calls"><h2 id="calls" className={styles.sectionTitle}>Nemotron calls</h2>
      <div className="table-scroll"><table aria-label="Provider calls"><thead><tr><th className="num">Call</th><th>Outcome</th>
        <th className="num">Reserved ceiling</th><th className="num">Reported tokens</th><th className="num">Seconds</th></tr></thead>
        <tbody>{calls.map(call => <tr key={call.sequence}><td className="num">{call.sequence}</td>
          <td>{call.error ? `${call.status}: ${call.error.replace(/_/g, " ")}` : call.status}{call.feedback ? <div className={styles.reason}>Not run: {call.feedback}</div> : null}</td>
          <td className="num">{call.reservedCompletionTokens ?? "—"}</td><td className="num">{call.usage?.completion_tokens ?? "—"}</td><td className="num">{call.elapsedSeconds ?? "—"}</td></tr>)}</tbody></table></div></section>}
    <section aria-labelledby="proposals"><h2 id="proposals" className={styles.sectionTitle}>Proposals{rejected > 0 && <span className={styles.outOf}> · {rejected} rejected, not counted as tests</span>}</h2>
      <p className={styles.footnote}>Reasons and hypotheses are unverified text; only measured results are evidence.</p>
      <Proposals proposals={data.proposals} /></section>
    <p className={styles.footnote}>Model setup: {data.context}. Failure patterns: {data.discoveryFamilies.join(", ") || "None"}. Criterion: {data.criterion?.candidate ?? "Not set"}.</p>
  </div>;
}

function Proposals({ proposals }: { proposals: ProposalDetail[] }) {
  return <StateBlock empty={proposals.length === 0}>
    <div className="table-scroll"><table className={styles.proposalsTable} aria-label="Investigation proposals"><thead><tr><th className="num">#</th><th>Case</th><th>Status</th><th>Hypothesis or reason</th></tr></thead>
      <tbody>{proposals.map(item => {
        const hypothesis = item.hypothesis as { suspected?: string; supportIf?: string; weakenIf?: string } | null;
        return <tr key={item.id}><td className="num">{item.sequence}</td><td><strong>{caseTitle(item.scenario)}</strong><div className={styles.reason}>{describeCase(item.scenario)}</div></td>
          <td><Badge tone={item.status === "rejected" ? "warn" : "neutral"}>{item.status.replace(/_/g, " ")}</Badge>{item.rejection ? <div className={styles.reason}>{item.rejection}</div> : null}</td>
          <td>{hypothesis ? <><strong>Hypothesis:</strong> {hypothesis.suspected} <span className={styles.footnote}>Supported if {hypothesis.supportIf}; weakened if {hypothesis.weakenIf}</span></> : item.reason}</td></tr>;
      })}</tbody></table></div>
  </StateBlock>;
}
