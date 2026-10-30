import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Download } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";
import { Select } from "@/registry/components/select/select";
import { api, ApiError, investigations } from "../api/client";
import type { ContextInfo, Finding, InvestigationView, ProposalDetail, RecordedInvestigation } from "../api/types";
import { Badge, Button, Callout, Panel, StateBlock, type Tone } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { percent } from "../format";
import styles from "./investigations.module.css";

const errorText = (error: unknown) => error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Request failed. Try again.";
const requestId = () => crypto.randomUUID().replace(/-/g, "");

const stops: Record<string, [string, Tone]> = {
  completed: ["All proposals run", "ok"], model_stopped: ["Nemotron stopped", "info"], budget_exhausted: ["Experiment budget used", "warn"],
  experiment_limit: ["Experiment budget used", "warn"], failure_limit: ["Failure limit reached", "bad"], cancelled: ["Cancelled", "neutral"],
  time_limit: ["Time limit reached", "warn"], evaluator_budget: ["Evaluator limit reached", "warn"], call_limit: ["Provider call limit reached", "warn"],
  token_limit: ["Token allowance used", "warn"], proposal_limit: ["Proposal limit reached", "warn"], input_limit: ["Input limit reached", "warn"],
  provider_error: ["Provider error", "bad"], invalid_response: ["Invalid provider response", "bad"]
};
const findingTones: Record<Finding["status"], [string, Tone]> = {
  measured_failure: ["Measured failure", "bad"], no_measured_failure: ["No measured failure", "ok"], inconclusive: ["Inconclusive", "warn"],
  not_applicable: ["Not applicable", "neutral"], invalid_proposal: ["Rejected proposal", "neutral"], execution_error: ["Execution error", "bad"]
};

interface Component { sensor: string; kind: string; onset_before_failure?: number | null; severity_sd?: number | null; sign?: number | null; length?: number | null }

export function describeCase(scenario: Record<string, unknown> | null | undefined) {
  const components = (scenario?.components ?? []) as Component[];
  if (!components.length) return "Unreadable case";
  return components.map(item => {
    const drift = item.kind === "drift" && item.severity_sd ? ` ${item.sign === -1 ? "−" : "+"}${item.severity_sd} SD` : "";
    const timing = item.onset_before_failure ? ` from ${item.onset_before_failure} cycles before failure` : " at a seeded onset";
    return `${item.sensor} ${item.kind}${drift}${item.length ? ` for ${item.length} cycles` : ""}${timing}`;
  }).join(" + ");
}

export function Investigations() {
  const health = useApi(() => api.health(), []);
  return <StateBlock loading={health.loading} error={health.error}>
    <header className="page-head"><h1>Fault investigations</h1><p>Search for sensor faults that cost useful warnings, then reduce, replay and compare remedies on fixed development models.</p></header>
    {health.data?.mode === "full" ? <Workspace /> : <>
      <Panel title="Run investigations locally"><p>Live investigations use fitted contexts on a local server, so this site cannot start them or call Nemotron. Below are recorded runs.</p></Panel>
      <Recorded />
    </>}
  </StateBlock>;
}

interface RecordedRow { ref: string; family: string; status: Finding["status"]; chosenBy?: string; evaluatedHistories: number; expectedHistories: number;
  cleanDetection: number | null; faultedDetection: number | null }
interface RecordedEvidence { generatedAt: string; digest: string; demonstration?: { note: string } | null; experiments: RecordedRow[];
  controller?: { model: string; prompt: string; callsUsed: number; reservedCompletionTokens: number; reportedCompletionTokens: number } | null;
  reductions: { status: string; family: string; claims: string[] }[]; remedies: { threshold: number | null; improved: number; degraded: number; stillFailing?: number }[];
  validations?: { status: string; freshHistories: number; cases: { label: string; original: { status: string }; remedy?: { status: string } }[] }[] }

function Recorded() {
  const recorded = useApi(() => investigations.recorded(), []);
  return <StateBlock loading={recorded.loading} error={recorded.error} empty={recorded.data?.length === 0}>
    {recorded.data?.map(item => <RecordedRun key={item.name} item={item} />)}
  </StateBlock>;
}

function RecordedRun({ item }: { item: RecordedInvestigation }) {
  const evidence = item.evidence as unknown as RecordedEvidence;
  const controller = evidence.controller;
  return <Panel title={`Recorded: ${item.name}`} aside={<Badge tone="neutral">Recorded, not live</Badge>}
    description={`Generated ${evidence.generatedAt}. Digest ${evidence.digest.slice(0, 12)}.`}>
    <div className={styles.stack}>
      {evidence.demonstration && <Callout tone="warn" title="Demonstration setting">{evidence.demonstration.note.replace(/^Demonstration setting:\s*/, "")}</Callout>}
      <p>{controller ? `Nemotron (${controller.model}, ${controller.prompt}) used ${controller.callsUsed} ${controller.callsUsed === 1 ? "call" : "calls"}: ${controller.reportedCompletionTokens} reported completion tokens within a reserved ceiling of ${controller.reservedCompletionTokens}.`
        : "No Nemotron calls; every case was supplied."}</p>
      <div className="table-scroll"><table aria-label={`Recorded experiments: ${item.name}`}><thead><tr><th>Result</th><th>Case family</th><th>Chosen by</th><th>Status</th>
        <th className="num">Coverage</th><th className="num">Useful warnings</th></tr></thead>
        <tbody>{evidence.experiments.map(row => <tr key={row.ref}><td>{row.ref}</td><td>{row.family}</td><td>{row.chosenBy === "nemotron" ? "Nemotron" : "Supplied"}</td>
          <td><Badge tone={findingTones[row.status][1]}>{findingTones[row.status][0]}</Badge></td><td className="num">{row.evaluatedHistories} / {row.expectedHistories}</td>
          <td className="num">{percent(row.cleanDetection)} → {percent(row.faultedDetection)}</td></tr>)}</tbody></table></div>
      {evidence.reductions.map((reduction, index) => <p key={index}><strong>Reduction ({reduction.status}):</strong> {reduction.family}. {reduction.claims.join(" ")}</p>)}
      {evidence.remedies.map((remedy, index) => <p key={index}><strong>Remedy, threshold {remedy.threshold}:</strong> {remedy.improved} improved, {remedy.degraded} degraded
        {remedy.stillFailing !== undefined ? `, ${remedy.stillFailing} still failing` : ""}. Development-only; it needs fresh validation.</p>)}
      {evidence.validations?.map((validation, index) => <p key={index}><strong>Validation on {validation.freshHistories} fresh histories ({validation.status}):</strong>{" "}
        {validation.cases.map(row => `${row.label} ${row.original.status.replace(/_/g, " ")}${row.remedy ? ` (with remedy: ${row.remedy.status.replace(/_/g, " ")})` : ""}`).join("; ")}.</p>)}
    </div>
  </Panel>;
}

function Workspace() {
  const contexts = useApi(() => investigations.contexts(), []);
  const saved = useApi(() => investigations.list(), []);
  const first = contexts.data?.[0];
  return <>
    <StateBlock loading={contexts.loading} error={contexts.error}>
      {contexts.data && (first ? <CreateForm contexts={contexts.data} initial={first} /> : <Panel title="No fitted context yet">
        <p>Create one from the repository root, then refresh this page:</p>
        <pre className={styles.command}>python scripts/evaluate_fault_scenarios.py --profile synthetic-rotating-v1 --output artifacts/investigations/contexts/synthetic</pre>
      </Panel>)}
    </StateBlock>
    <Panel title="Saved investigations" tight>
      <StateBlock loading={saved.loading} error={saved.error} empty={saved.data?.length === 0}>
        <div className="table-scroll"><table><thead><tr><th>Objective</th><th>Context</th><th className="num">Experiments</th><th className="num">Measured failures</th><th>Status</th></tr></thead>
          <tbody>{saved.data?.map(item => <tr key={item.id}>
            <td><Link to={`/investigations/${item.id}`}>{item.objective}</Link></td><td>{item.context}</td>
            <td className="num">{item.experimentsUsed} / {item.maxExperiments}</td><td className="num">{item.discoveries}</td>
            <td>{item.active ? <Badge tone="info">Running {item.active}</Badge> : item.stopReason ? <Badge tone={stops[item.stopReason]?.[1]}>{stops[item.stopReason]?.[0] ?? item.stopReason}</Badge> : <Badge>Not started</Badge>}</td>
          </tr>)}</tbody></table></div>
      </StateBlock>
    </Panel>
  </>;
}

function CreateForm({ contexts, initial }: { contexts: ContextInfo[]; initial: ContextInfo }) {
  const navigate = useNavigate();
  const [contextName, setContextName] = useState(initial.name);
  const context = contexts.find(item => item.name === contextName) ?? initial;
  const models = Object.keys(context.thresholds);
  const [candidate, setCandidate] = useState(models[0] ?? "");
  const [objective, setObjective] = useState("Find sensor faults that cost useful warnings.");
  const [experiments, setExperiments] = useState("16");
  const [seed, setSeed] = useState("3");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const target = models.includes(candidate) ? candidate : models[0] ?? "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const created = await investigations.create({ context: context.name, objective, maxExperiments: Number(experiments), seed: Number(seed), criterion: { candidate: target } });
      navigate(`/investigations/${created.id}`);
    } catch (failure) { setError(errorText(failure)); setBusy(false); }
  }

  return <Panel title="New investigation" description="The fitted models, thresholds, fault profile and data stay fixed for the whole search.">
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.fields}>
        <Select label="Fitted context" value={context.name} onValueChange={value => setContextName(String(value))} options={contexts.map(item => ({ value: item.name, label: item.name }))} />
        <Select label="Model under test" value={target} onValueChange={value => setCandidate(String(value))} options={models.map(name => ({ value: name, label: name }))} />
      </div>
      <div className="table-scroll"><table aria-label="Clean performance"><thead><tr><th>Model</th><th className="num">Threshold</th><th className="num">Useful warnings</th><th className="num">Early alarm burden</th><th className="num">Histories</th></tr></thead>
        <tbody>{models.map(name => <tr key={name}><td>{name}</td><td className="num">{context.thresholds[name]}</td><td className="num">{percent(context.clean[name]?.detection)}</td>
          <td className="num">{percent(context.clean[name]?.alarmBurden, 1)}</td><td className="num">{context.clean[name]?.histories}</td></tr>)}</tbody></table></div>
      <p className={styles.footnote}>Clean development performance{context.profile ? `; fault profile ${context.profile}` : "; no fault profile"}. A measured failure needs adequate clean behavior first.</p>
      <Textarea label="Concern" value={objective} maxLength={2000} onChange={event => setObjective(event.target.value)} />
      <div className={styles.fields}>
        <Input label="Experiment budget" type="number" min={1} max={128} value={experiments} onChange={event => setExperiments(event.target.value)} />
        <Input label="Seed cases" description="Single-channel checks run before any model choice." type="number" min={0} max={12} value={seed} onChange={event => setSeed(event.target.value)} />
      </div>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div className={styles.actions}><Button type="submit" variant="primary" loading={busy}>Create investigation</Button></div>
    </form>
  </Panel>;
}

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
    {data && <Detail data={data} reload={reload} />}
  </StateBlock>;
}

function Detail({ data, reload }: { data: InvestigationView; reload: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const lastEvent = data.events.at(-1);
  const failed = lastEvent?.kind.startsWith("failed:") ? lastEvent : null;
  const rejected = data.proposals.filter(item => item.status === "rejected").length;

  async function act(label: string, action: () => Promise<unknown>) {
    setBusy(label); setError("");
    try { await action(); reload(); } catch (failure) { setError(errorText(failure)); } finally { setBusy(""); }
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
    });
  }

  const status = data.active ? ["Running " + data.active, "info"] as const : data.stopReason ? stops[data.stopReason] ?? [data.stopReason, "neutral"] as const : ["Not started", "neutral"] as const;
  return <>
    <header className={`page-head ${styles.heading}`}>
      <div><h1>{data.objective}</h1><p>Context {data.context}. Opening this page never starts work.</p></div>
      <Badge tone={status[1]}>{status[0]}</Badge>
    </header>
    <dl className={styles.summary}>
      <div><dt>Experiments used</dt><dd>{data.experimentsUsed} / {data.maxExperiments}</dd></div>
      <div><dt>Measured failures</dt><dd>{data.discoveries}</dd></div>
      <div><dt>Failure families</dt><dd>{data.discoveryFamilies.length ? data.discoveryFamilies.join(", ") : "None"}</dd></div>
      <div><dt>Rejected proposals</dt><dd>{rejected}</dd></div>
    </dl>
    {failed && <Callout tone="fault" title="The last operation failed">{failed.detail}</Callout>}
    {lastEvent?.kind === "interrupted" && <Callout tone="warn" title="Interrupted">{lastEvent.detail} Start again to recover within the saved limits.</Callout>}
    {data.state.cancel_requested && !data.active && <Callout tone="warn" title="Cancellation is saved">Resume before starting more work.</Callout>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
    <Controls data={data} busy={busy} act={act} />
    <Findings data={data} busy={busy} act={act} />
    <Timeline data={data} />
    <Proposals proposals={data.proposals} />
    {data.reductions.length > 0 && <Reductions reductions={data.reductions} />}
    <Remedies data={data} busy={busy} act={act} />
    <div className={styles.actions}>
      <Button variant="secondary" onClick={() => exportEvidence("export")} loading={busy === "export"}><Download size={16} aria-hidden="true" />Export evidence</Button>
      <Button variant="ghost" onClick={() => exportEvidence("public")} loading={busy === "public"}><Download size={16} aria-hidden="true" />Public evidence</Button>
      <span className={styles.footnote}>Public evidence leaves out the concern, equipment IDs and raw readings.</span>
    </div>
  </>;
}

type Act = (label: string, action: () => Promise<unknown>) => Promise<void>;

function Controls({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const [allow, setAllow] = useState(false);
  const [calls, setCalls] = useState("4");
  const [tokens, setTokens] = useState("32768");
  const controller = data.controller as { callsUsed?: number; reservedCompletionTokens?: number; reportedCompletionTokens?: number } | null;
  const locked = Boolean(data.active) || data.state.cancel_requested;
  if (data.active) return <Panel title="Running" aside={<Button variant="danger" onClick={() => act("cancel", () => investigations.cancel(data.id))} loading={busy === "cancel"}>Cancel</Button>}>
    <p>Results appear below as each experiment is saved. Cancelling stops at the next safe point.</p>
  </Panel>;
  return <Panel title="Run experiments" aside={data.state.cancel_requested ? <Button onClick={() => act("resume", () => investigations.resume(data.id))} loading={busy === "resume"}>Resume</Button> : undefined}>
    <div className={styles.stack}>
      <div className={styles.actions}>
        <Button disabled={locked} loading={busy === "run"} onClick={() => act("run", () => investigations.start(data.id, { requestId: requestId(), mode: "run" }))}>Run saved proposals</Button>
        <span className={styles.footnote}>Local only. No provider request.</span>
      </div>
      <fieldset className={styles.preview}>
        <legend>Nemotron search</legend>
        <p>Sent to Nebius for each call: your concern, channel aliases with reviewed descriptions, fault bounds, clean performance and aggregate matched results.</p>
        <p>Never sent: sensor names, raw readings, equipment IDs, fitted models or keys. Workspace AI permission is also required.</p>
        <div className={styles.fields}>
          <Input label="Provider calls" type="number" min={1} max={64} value={calls} onChange={event => setCalls(event.target.value)} />
          <Input label="Completion token ceiling" description="A reserved ceiling, not actual usage or cost." type="number" min={1} value={tokens} onChange={event => setTokens(event.target.value)} />
        </div>
        <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow sending this information to Nebius for this run</label>
        <div className={styles.actions}>
          <Button variant="primary" disabled={!allow || locked} loading={busy === "agent"} onClick={() => act("agent", () => investigations.start(data.id, { requestId: requestId(), mode: "agent", allowProvider: true, maxProviderCalls: Number(calls), maxCompletionTokens: Number(tokens) }))}>Start Nemotron search</Button>
          {controller && <span className={styles.footnote}>Calls used {controller.callsUsed ?? 0}; reserved {controller.reservedCompletionTokens ?? 0} tokens; reported {controller.reportedCompletionTokens ?? 0}.</span>}
        </div>
      </fieldset>
    </div>
  </Panel>;
}

function Findings({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const measured = data.findings.filter(item => item.attempt_id);
  if (!data.criterion) return <Panel title="Findings"><p>This investigation has no finding criterion, so results are not classified.</p></Panel>;
  return <Panel title="Findings" description={`Classified by code for ${data.criterion.candidate}. Numbers are measured on matched development histories.`}>
    {measured.length === 0 ? <p>No experiment has finished yet.</p> : <div className={styles.stack}>
      {measured.map(finding => <FindingCard key={finding.attempt_id} finding={finding} data={data} busy={busy} act={act} />)}
    </div>}
  </Panel>;
}

function FindingCard({ finding, data, busy, act }: { finding: Finding; data: InvestigationView; busy: string; act: Act }) {
  const [replay, setReplay] = useState<string>("");
  const [label, tone] = findingTones[finding.status];
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  const attempt = finding.attempt_id ?? "";
  const chosen = controllerCalls(data).some(call => call.proposalId === finding.proposal_id);
  const partial = (finding.evaluated_histories ?? 0) < (finding.expected_histories ?? 0);
  const unscored = finding.status === "not_applicable" || finding.status === "inconclusive";
  return <article className={styles.finding} aria-label={`${label}: ${finding.family ?? "case"}`}>
    <header><Badge tone={tone}>{label}</Badge>{partial && finding.status !== "execution_error" && <Badge tone="warn">Partial coverage</Badge>}
      <Badge tone={chosen ? "info" : "neutral"}>{chosen ? "Chosen by Nemotron" : "Supplied case"}</Badge><strong>{describeCase(proposal?.scenario)}</strong></header>
    {finding.status === "execution_error" ? <p>{finding.reasons?.[0]}</p> : <>
      <dl className={styles.metrics}>
        <div><dt>Coverage</dt><dd>{finding.evaluated_histories ?? 0} / {finding.expected_histories ?? 0} histories</dd></div>
        <div><dt>Useful warnings</dt><dd>{percent(finding.clean_detection)} → {percent(finding.faulted_detection)}</dd></div>
        <div><dt>Early alarm burden</dt><dd>{percent(finding.clean_burden, 1)} → {percent(finding.faulted_burden, 1)}</dd></div>
      </dl>
      {unscored && <p><strong>Why this was not scored as a finding:</strong></p>}
      {finding.reasons?.map(reason => <p key={reason} className={styles.reason}>{reason}</p>)}
      {finding.effects?.map(effect => <p key={effect.kind}>{effect.kind.replace(/_/g, " ")}: {effect.histories.length} histories</p>)}
      {(finding.support?.length ?? 0) > 0 && <details><summary>{finding.support?.length} histories changed</summary>
        <div className="table-scroll"><table><thead><tr><th>History</th><th>Clean</th><th>Faulted</th><th className="num">Lead</th></tr></thead>
          <tbody>{finding.support?.map(row => <tr key={row.equipment_id}><td>{row.equipment_id}</td><td>{row.clean}</td><td>{row.faulted}</td>
            <td className="num">{row.clean_lead ?? "—"} → {row.faulted_lead ?? "—"}</td></tr>)}</tbody></table></div>
      </details>}
      {(finding.assumptions?.length ?? 0) > 0 && <details><summary>Profile assumptions</summary><ul>{finding.assumptions?.map(item => <li key={item}>{item}</li>)}</ul></details>}
      <div className={styles.actions}>
        {finding.status === "measured_failure" && <Button disabled={Boolean(data.active)} loading={busy === `reduce-${attempt}`}
          onClick={() => act(`reduce-${attempt}`, () => investigations.reduce(data.id, { requestId: requestId(), attempt, maxExperiments: 16 }))}>Reduce</Button>}
        <Button variant="ghost" loading={busy === `replay-${attempt}`} onClick={() => act(`replay-${attempt}`, async () => {
          const check = await investigations.replay(data.id, attempt);
          setReplay(check.matches ? "Replay reproduced this result exactly." : "Replay did not reproduce this result.");
        })}>Replay</Button>
        {replay && <span role="status" className={styles.footnote}>{replay}</span>}
      </div>
      <FaultResearch finding={finding} data={data} busy={busy} act={act} />
    </>}
  </article>;
}

function FaultResearch({ finding, data, busy, act }: { finding: Finding; data: InvestigationView; busy: string; act: Act }) {
  const [open, setOpen] = useState(false);
  const [allow, setAllow] = useState(false);
  const attempt = finding.attempt_id ?? "";
  const report = data.research?.find(item => item.attempt === attempt);
  const proposal = data.proposals.find(item => item.id === finding.proposal_id);
  const components = (proposal?.scenario?.components ?? []) as Component[];
  const kinds = [...new Set(components.map(item => item.kind))].sort().join(" ");
  const query = `industrial sensor ${kinds} readings troubleshooting manufacturer documentation predictive maintenance`;
  const sources = (ids: string[]) => (report?.sources ?? []).filter(source => ids.includes(source.id)).map(source =>
    <a key={source.id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>);
  if (report) return <div className={styles.stack}>
    <strong>Fault research · {report.status}</strong>
    <p className={styles.footnote}>External references and AI suggestions; separate from measured findings. Sources do not validate the fault policy or prove a physical cause.</p>
    {report.error && <p role="status">{report.error}</p>}
    {report.note && <>
      <p>{report.note.summary}</p><div className={styles.actions}>{sources(report.note.sourceIds)}</div>
      {report.note.tests.map((test, index) => <div key={index}><strong>{test.action}</strong><p>{test.reason}</p>
        <div className={styles.actions}>{sources(test.sourceIds)}</div></div>)}
      <details><summary>Saved source excerpts and search</summary><p>{report.query}</p>{(report.sources ?? []).map(source =>
        <div key={source.id}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a><p>{source.content}</p></div>)}</details>
    </>}
    <span className={styles.footnote}>Tavily searches {report.searchRequests}; Nemotron requests {report.modelRequests}; reserved completion ceiling {report.reservedCompletionTokens}; reported tokens {report.reportedCompletionTokens ?? "unavailable"}. Saved results are reused.</span>
  </div>;
  return <div className={styles.stack}>
    <Button variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>Research this fault</Button>
    {open && <fieldset className={styles.preview}><legend>Research this fault</legend>
      <p>Tavily receives this search:</p><p>{query}</p>
      <p>Nemotron receives up to three source excerpts and aliased aggregate experiment results. No raw readings, sensor names, equipment IDs or private concern are sent.</p>
      <p>One search and one Nemotron request, with at most 5,120 completion tokens. References are unverified context and do not change your measured findings. Workspace AI permission is also required.</p>
      <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow Tavily search and Nemotron research for this fault</label>
      <Button disabled={!allow || Boolean(data.active) || data.state.cancel_requested} loading={busy === `research-${attempt}`}
        onClick={() => act(`research-${attempt}`, () => investigations.research(data.id, { requestId: requestId(), attempt, allowResearch: true }))}>Start fault research</Button>
    </fieldset>}
  </div>;
}

const eventLabels: Record<string, string> = { created: "Created", cancel_requested: "Cancellation requested", resumed: "Resumed", interrupted: "Interrupted" };

interface ControllerCall { sequence: number; status: string; proposalId?: string | null; error?: string | null; feedback?: string | null;
  reservedCompletionTokens?: number; usage?: { completion_tokens?: number } | null; elapsedSeconds?: number | null }

const controllerCalls = (data: InvestigationView) => ((data.controller as { calls?: ControllerCall[] } | null)?.calls) ?? [];

function Timeline({ data }: { data: InvestigationView }) {
  const calls = controllerCalls(data);
  return <Panel title="Timeline">
    <ol className={styles.timeline}>
      {[...data.events].reverse().map(event => {
        const [kind, operation] = event.kind.split(":");
        const text = operation ? `${kind === "started" ? "Started" : kind === "finished" ? "Finished" : "Failed"} ${operation}` : eventLabels[event.kind] ?? event.kind;
        return <li key={event.sequence}><time dateTime={new Date(event.at * 1000).toISOString()}>{new Date(event.at * 1000).toLocaleTimeString()}</time>
          <span>{text}{event.detail ? `: ${stops[event.detail]?.[0] ?? event.detail}` : ""}</span></li>;
      })}
    </ol>
    {calls.length > 0 && <div className="table-scroll"><table aria-label="Provider calls"><thead><tr><th className="num">Call</th><th>Outcome</th>
      <th className="num">Reserved ceiling</th><th className="num">Reported tokens</th><th className="num">Seconds</th></tr></thead>
      <tbody>{calls.map(call => <tr key={call.sequence}><td className="num">{call.sequence}</td>
        <td>{call.error ? `${call.status}: ${call.error.replace(/_/g, " ")}` : call.status}{call.feedback ? <div className={styles.reason}>Not run: {call.feedback}</div> : null}</td>
        <td className="num">{call.reservedCompletionTokens ?? "—"}</td><td className="num">{call.usage?.completion_tokens ?? "—"}</td><td className="num">{call.elapsedSeconds ?? "—"}</td></tr>)}</tbody></table></div>}
  </Panel>;
}

function Proposals({ proposals }: { proposals: ProposalDetail[] }) {
  return <Panel title="Proposals" description="Reasons and hypotheses are unverified text; only measured results above are evidence." tight>
    <StateBlock empty={proposals.length === 0}>
      <div className="table-scroll"><table><thead><tr><th className="num">#</th><th>Case</th><th>Status</th><th>Hypothesis or reason</th></tr></thead>
        <tbody>{proposals.map(item => {
          const hypothesis = item.hypothesis as { suspected?: string; supportIf?: string; weakenIf?: string } | null;
          return <tr key={item.id}><td className="num">{item.sequence}</td><td>{describeCase(item.scenario)}</td>
            <td>{item.status}{item.rejection ? <div className={styles.reason}>{item.rejection}</div> : null}</td>
            <td>{hypothesis ? <><strong>Hypothesis:</strong> {hypothesis.suspected} <span className={styles.footnote}>Supported if {hypothesis.supportIf}; weakened if {hypothesis.weakenIf}</span></> : item.reason}</td></tr>;
        })}</tbody></table></div>
    </StateBlock>
  </Panel>;
}

function Reductions({ reductions }: { reductions: Record<string, unknown>[] }) {
  return <Panel title="Reductions">
    <div className={styles.stack}>{reductions.map(item => {
      const reduction = item as { id: string; status: string; experiments: number; claims: string[]; original: Record<string, unknown>; final: Record<string, unknown> | null; steps: unknown[] };
      return <article key={reduction.id} className={styles.finding}>
        <header><Badge tone={reduction.status === "complete" ? "ok" : "warn"}>{reduction.status}</Badge><strong>{describeCase(reduction.final ?? reduction.original)}</strong></header>
        <p>From {describeCase(reduction.original)}. {reduction.steps.length} steps, {reduction.experiments} new experiments.</p>
        <ul>{reduction.claims.map(claim => <li key={claim}>{claim}</li>)}</ul>
      </article>;
    })}</div>
  </Panel>;
}

function Remedies({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const [kind, setKind] = useState<"threshold" | "augmented">("threshold");
  const [threshold, setThreshold] = useState("0.5");
  const [approve, setApprove] = useState(false);
  const ready = data.discoveries > 0 || data.reductions.length > 0;
  const reports = useMemo(() => data.remedies as { id: string; kind: string; threshold: number | null; improved: number; degraded: number; meetsCriteria: boolean;
    clean: { original: { detection: number; alarmBurden: number | null }; remedy: { detection: number; alarmBurden: number | null } }; note: string }[], [data.remedies]);
  return <Panel title="Remedies" description="Compared on every discovered, reduced and previously passing case. Nothing replaces a deployed model.">
    <div className={styles.stack}>
      {ready ? <div className={styles.fields}>
        <Select label="Remedy" value={kind} onValueChange={value => setKind(value as "threshold" | "augmented")} options={[{ value: "threshold", label: "Explicit warning threshold" }, { value: "augmented", label: "Augmented retraining" }]} />
        {kind === "threshold" ? <Input label="Threshold" type="number" step="0.01" value={threshold} onChange={event => setThreshold(event.target.value)} />
          : <label className={styles.check}><input type="checkbox" checked={approve} onChange={event => setApprove(event.target.checked)} />Approve development-only retraining</label>}
      </div> : <p>Find or reduce a measured failure first.</p>}
      {ready && <div className={styles.actions}><Button disabled={Boolean(data.active) || (kind === "augmented" && !approve)} loading={busy === "remedy"}
        onClick={() => act("remedy", () => investigations.remedy(data.id, { requestId: requestId(), kind, threshold: kind === "threshold" ? Number(threshold) : null, approveTraining: approve }))}>Compare remedy</Button></div>}
      {reports.map(report => <article key={report.id} className={styles.finding}>
        <header><Badge tone={report.meetsCriteria ? "ok" : "bad"}>{report.meetsCriteria ? "Meets criteria" : "Fails criteria"}</Badge>
          <strong>{report.kind === "threshold" ? `Threshold ${report.threshold}` : "Augmented retraining"}</strong></header>
        <dl className={styles.metrics}>
          <div><dt>Improved cases</dt><dd>{report.improved}</dd></div><div><dt>Degraded cases</dt><dd>{report.degraded}</dd></div>
          <div><dt>Clean useful warnings</dt><dd>{percent(report.clean.original.detection)} → {percent(report.clean.remedy.detection)}</dd></div>
          <div><dt>Clean alarm burden</dt><dd>{percent(report.clean.original.alarmBurden, 1)} → {percent(report.clean.remedy.alarmBurden, 1)}</dd></div>
        </dl>
        <p className={styles.footnote}>{report.note}</p>
      </article>)}
    </div>
  </Panel>;
}
