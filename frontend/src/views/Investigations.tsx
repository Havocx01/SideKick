import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Download, FlaskConical } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";
import { Select } from "@/registry/components/select/select";
import { api, ApiError, investigations } from "../api/client";
import type { ContextInfo, Finding, InvestigationView, ProposalDetail, RecordedInvestigation } from "../api/types";
import { Badge, Button, Callout, Panel, StateBlock, type Tone } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { candidateLabel, percent } from "../format";
import { ContextSetup } from "../components/investigations/ContextSetup";
import { Disclosure } from "../components/investigations/Disclosure";
import { WarningComparison } from "../components/investigations/WarningComparison";
import { RollingNumber } from "../components/cult/RollingNumber";
import styles from "./investigations.module.css";

const errorText = (error: unknown) => error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Request failed. Try again.";
const histories = (count: number) => `${count} ${count === 1 ? "history" : "histories"}`;
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

function caseTitle(scenario: Record<string, unknown> | null | undefined) {
  const names: Record<string, string> = { temp_bearing: "Bearing temperature", vibration_rms: "Vibration", oil_particles: "Oil particles", pressure_out: "Outlet pressure", flow_rate: "Flow rate", current_draw: "Current draw" };
  const faults: Record<string, string> = { dropout: "missing readings", stuck: "held constant", drift: "drifting" };
  const components = (scenario?.components ?? []) as Component[];
  return components.length ? components.map(item => `${names[item.sensor] ?? item.sensor.replace(/_/g, " ")}: ${faults[item.kind] ?? item.kind}`).join(" + ") : "Unreadable fault test";
}

export function Investigations() {
  const health = useApi(() => api.health(), []);
  return <StateBlock loading={health.loading} error={health.error}>
    <header className="page-head"><h1>Fault investigations</h1><p>Find the sensor faults that make a model miss useful warnings, then test a fix.</p></header>
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
  const titles: Record<string, string> = { "nemotron-live-recorded": "Nemotron search", "compound-demo-recorded": "A combined sensor failure", "fresh-validation-recorded": "Checking a fix on fresh data", "synthetic-recorded": "Initial sensor checks",
    "nemotron-live-default": "Nemotron search on the default model", "nemotron-live-browser": "A sensor failure proposed by Nemotron", "nemotron-live-demo": "A supplied sensor failure" };
  const focus = evidence.experiments.find(row => row.status === "measured_failure" && row.chosenBy === "nemotron")
    ?? evidence.experiments.find(row => row.status === "measured_failure") ?? evidence.experiments[0];
  const failures = evidence.experiments.filter(row => row.status === "measured_failure").length;
  return <Panel title={titles[item.name] ?? item.name.replace(/[-_]/g, " ")} aside={<Badge tone="neutral">Recorded, not live</Badge>}
    description="Saved synthetic development evidence. Opening this record does not run an experiment or make an AI request.">
    <div className={styles.stack}>
      {evidence.demonstration && <Callout tone="warn" title="Demonstration setting">{evidence.demonstration.note.replace(/^Demonstration setting:\s*(\w)/, (_, first: string) => first.toUpperCase())}</Callout>}
      <div className={styles.recordSummary}><span><strong>{evidence.experiments.length}</strong> saved tests</span><span><strong>{failures}</strong> measured {failures === 1 ? "failure" : "failures"}</span>
        <span>{controller ? `${controller.callsUsed} Nemotron ${controller.callsUsed === 1 ? "call" : "calls"}` : "Cases supplied by the builder"}</span></div>
      {focus && <div><div className={styles.heading}><h3>{focus.status === "measured_failure" ? "A fault that cost useful warnings" : focus.status === "no_measured_failure" ? "No measured failure in this test" : findingTones[focus.status][0]}</h3>
        <Badge tone={findingTones[focus.status][1]}>{findingTones[focus.status][0]}</Badge></div>
        <WarningComparison before={focus.cleanDetection} after={focus.faultedDetection} />
        <p className={styles.footnote}>{focus.evaluatedHistories} of {focus.expectedHistories} machine histories evaluated. {focus.chosenBy === "nemotron" ? "This case was proposed by Nemotron." : "This case was supplied by the builder."}</p></div>}
      <Disclosure title={`All recorded tests (${evidence.experiments.length})`} description="Individual outcomes, case families, coverage, and who chose each test.">
      <div className="table-scroll"><table aria-label={`Recorded experiments: ${item.name}`}><thead><tr><th>Result</th><th>Case family</th><th>Chosen by</th><th>Status</th>
        <th className="num">Coverage</th><th className="num">Useful warnings</th></tr></thead>
        <tbody>{evidence.experiments.map(row => <tr key={row.ref}><td>{row.ref}</td><td>{row.family}</td><td>{row.chosenBy === "nemotron" ? "Nemotron" : "Supplied"}</td>
          <td><Badge tone={findingTones[row.status][1]}>{findingTones[row.status][0]}</Badge></td><td className="num">{row.evaluatedHistories} / {row.expectedHistories}</td>
          <td className="num">{percent(row.cleanDetection)} → {percent(row.faultedDetection)}</td></tr>)}</tbody></table></div></Disclosure>
      {evidence.reductions.map((reduction, index) => <p key={index}><strong>Reduction ({reduction.status}):</strong> {reduction.family}. {reduction.claims.join(" ")}</p>)}
      {evidence.remedies.map((remedy, index) => <p key={index}><strong>Remedy, threshold {remedy.threshold}:</strong> {remedy.improved} improved, {remedy.degraded} degraded
        {remedy.stillFailing !== undefined ? `, ${remedy.stillFailing} still failing` : ""}. Development-only; it needs fresh validation.</p>)}
      {evidence.validations?.map((validation, index) => <p key={index}><strong>Validation on {validation.freshHistories} fresh histories ({validation.status}):</strong>{" "}
        {validation.cases.map(row => `${row.label} ${row.original.status.replace(/_/g, " ")}${row.remedy ? ` (with remedy: ${row.remedy.status.replace(/_/g, " ")})` : ""}`).join("; ")}.</p>)}
      <Disclosure title="Model usage and record details">
        <p>{controller ? `Nemotron (${controller.model}, ${controller.prompt}) used ${controller.callsUsed} ${controller.callsUsed === 1 ? "call" : "calls"}: ${controller.reportedCompletionTokens} reported completion tokens within a reserved ceiling of ${controller.reservedCompletionTokens}.`
          : "No Nemotron calls; every case was supplied."}</p><p className={styles.footnote}>Recorded at {evidence.generatedAt}. Record: {item.name}. Integrity digest: {evidence.digest}.</p>
      </Disclosure>
    </div>
  </Panel>;
}

function Workspace() {
  const contexts = useApi(() => investigations.contexts(), []);
  const saved = useApi(() => investigations.list(), []);
  const [lastContexts, setLastContexts] = useState<ContextInfo[] | null>(null);
  useEffect(() => { if (contexts.data) setLastContexts(contexts.data); }, [contexts.data]);
  const available = contexts.data ?? lastContexts;
  const first = available?.[0];
  return <>
    <ol className={styles.workflow} aria-label="Investigation workflow">
      <li data-current={!first || undefined}><span>{first ? <Check size={14} aria-hidden="true" /> : "1"}</span>Prepare models</li>
      <li data-current={!!first || undefined}><span>2</span>Choose your concern</li><li><span>3</span>Test sensor faults</li><li><span>4</span>Compare a fix</li>
    </ol>
    <ContextSetup ready={Boolean(first)} onReady={contexts.reload} />
    {available && contexts.error && <Callout tone="warn" title="Could not refresh model setups">Your current form is kept. <Button variant="ghost" onClick={contexts.reload}>Refresh model setups</Button></Callout>}
    <StateBlock loading={!available && contexts.loading} error={available ? null : contexts.error}>
      {available && first && <CreateForm contexts={available} initial={first} />}
    </StateBlock>
    <Panel title="Saved investigations" tight>
      <StateBlock loading={saved.loading} error={saved.error}>
        {saved.data?.length === 0 ? <div className={styles.empty}><FlaskConical size={23} aria-hidden="true" /><h3>No investigations yet</h3><p>Prepare your sample models above, then create an investigation. Your results will be saved here.</p></div>
          : <ul className={styles.savedList}>{saved.data?.map(item => <li key={item.id}>
            <Link to={`/investigations/${item.id}`} title={item.objective}><strong>{item.objective}</strong><span>{item.experimentsUsed} of {item.maxExperiments} tests used <span aria-hidden="true">·</span> {item.discoveries} measured {item.discoveries === 1 ? "failure" : "failures"}</span></Link>
            {item.active ? <Badge tone="info">Running {item.active}</Badge> : item.stopReason ? <Badge tone={stops[item.stopReason]?.[1]}>{stops[item.stopReason]?.[0] ?? item.stopReason}</Badge> : <Badge>Not started</Badge>}
            <ArrowRight size={16} aria-hidden="true" />
          </li>)}</ul>}
      </StateBlock>
    </Panel>
  </>;
}

function CreateForm({ contexts, initial }: { contexts: ContextInfo[]; initial: ContextInfo }) {
  const navigate = useNavigate();
  const [contextName, setContextName] = useState(initial.name);
  const context = contexts.find(item => item.name === contextName) ?? initial;
  const models = Object.keys(context.thresholds);
  const firstModel = models.find(name => !name.startsWith("age_baseline/")) ?? models[0] ?? "";
  const [candidate, setCandidate] = useState(firstModel);
  const [objective, setObjective] = useState("Find sensor faults that cost useful warnings.");
  const [experiments, setExperiments] = useState("16");
  const [seed, setSeed] = useState("3");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const target = models.includes(candidate) ? candidate : firstModel;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const created = await investigations.create({ context: context.name, objective, maxExperiments: Number(experiments), seed: Number(seed), criterion: { candidate: target } });
      navigate(`/investigations/${created.id}`);
    } catch (failure) { setError(errorText(failure)); setBusy(false); }
  }

  return <Panel title="New investigation" description="Choose what to investigate. Sidekick keeps the same models and data for every fault test.">
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.fields}>
        <Select label="Model setup" value={context.name} onValueChange={value => setContextName(String(value))} options={contexts.map(item => ({ value: item.name, label: item.name.startsWith("demo-fragile") ? `Sample with a fragile warning threshold (${item.name.slice(-6)})` : item.name.startsWith("synthetic-") ? `Rotating machine sample (${item.name.slice(-6)})` : item.name }))} />
        <Select label="Model under test" value={target} onValueChange={value => setCandidate(String(value))} options={models.map(name => {
          const [family, ...config] = name.split("/");
          return { value: name, label: candidateLabel(family ?? name, config.join("/") || undefined) };
        })} />
      </div>
      {target.startsWith("age_baseline/") && <p className={styles.footnote}>The age baseline uses elapsed age, not sensor readings. Select a sensor-based model to investigate the effect of sensor faults.</p>}
      <div className={styles.baseline} aria-label="Performance before sensor faults"><strong>Before sensor faults</strong><dl className={styles.metrics}>
        <div><dt>Useful warnings</dt><dd>{percent(context.clean[target]?.detection)}</dd></div><div><dt>Early alarm burden</dt><dd>{percent(context.clean[target]?.alarmBurden, 1)}</dd></div>
        <div><dt>Machine histories</dt><dd>{context.clean[target]?.histories}</dd></div></dl><p className={styles.footnote}>Development performance. A useful warning arrives early enough to act.</p></div>
      <Disclosure title="Model details and fault assumptions" description="Thresholds, model identifiers, and baseline performance for every model.">
        <div className="table-scroll"><table aria-label="Clean performance"><thead><tr><th>Model</th><th className="num">Threshold</th><th className="num">Useful warnings</th><th className="num">Early alarm burden</th><th className="num">Histories</th></tr></thead>
        <tbody>{models.map(name => <tr key={name}><td>{name}</td><td className="num">{context.thresholds[name]}</td><td className="num">{percent(context.clean[name]?.detection)}</td>
          <td className="num">{percent(context.clean[name]?.alarmBurden, 1)}</td><td className="num">{context.clean[name]?.histories}</td></tr>)}</tbody></table></div>
        <p className={styles.footnote}>Model setup: {context.name}. Fault profile: {context.profile ?? "None"}. Relationships in the profile are declared assumptions, not proof of physical causes.</p>
      </Disclosure>
      <Textarea label="Concern" value={objective} maxLength={2000} onChange={event => setObjective(event.target.value)} />
      <div className={styles.fields}>
        <Input label="Experiment budget" description="Maximum fault tests. Each test uses one slot." type="number" required min={1} max={128} value={experiments} onChange={event => setExperiments(event.target.value)} />
        <Input label="Initial checks" description="Known single-sensor faults to test first. These use your experiment budget." type="number" required min={0} max={Math.min(12, Number(experiments) || 12)} value={seed} onChange={event => setSeed(event.target.value)} />
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
    {data && view.error && <Callout tone="warn" title="Showing the last saved results"><p>The latest status could not be loaded. Your saved results are still available.</p><Button variant="secondary" onClick={reload}>Refresh investigation status</Button></Callout>}
    {data && <Detail data={data} reload={reload} />}
  </StateBlock>;
}

function Detail({ data, reload }: { data: InvestigationView; reload: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const pending = useRef(false);
  const lastEvent = data.events.at(-1);
  const failed = lastEvent?.kind.startsWith("failed:") ? lastEvent : null;
  const rejected = data.proposals.filter(item => item.status === "rejected").length;

  async function act(label: string, action: () => Promise<unknown>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(label); setError("");
    try { await action(); reload(); } catch (failure) { setError(errorText(failure)); } finally { setBusy(""); pending.current = false; }
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
  return <>
    <header className={`page-head ${styles.heading}`}>
      <div><Link className={styles.backLink} to="/investigations"><ArrowLeft size={14} aria-hidden="true" />All investigations</Link><h1>{data.objective}</h1><p>Fixed models. Matched machine histories. Results are saved as each test finishes.</p></div>
      <Badge tone={status[1]}>{status[0]}</Badge>
    </header>
    <dl className={styles.summary}>
      <div><dt>Fault tests used</dt><dd><RollingNumber value={data.experimentsUsed} /><span className={styles.outOf}> / {data.maxExperiments}</span></dd><div className={styles.budgetTrack} aria-hidden="true"><span style={{ width: `${Math.min(100, data.experimentsUsed / data.maxExperiments * 100)}%` }} /></div></div>
      <div><dt>Measured failures</dt><dd><RollingNumber value={data.discoveries} /></dd><p className={styles.footnote}>Faults that met the saved failure criterion</p></div>
      <div><dt>Distinct failure patterns</dt><dd><RollingNumber value={data.discoveryFamilies.length} /></dd><p className={styles.footnote}>{rejected} rejected {rejected === 1 ? "proposal" : "proposals"}, not counted as tests</p></div>
    </dl>
    {failed && <Callout tone="fault" title="The last operation failed">{failed.detail}</Callout>}
    {lastEvent?.kind === "interrupted" && <Callout tone="warn" title="Interrupted">{lastEvent.detail} Start again to recover within the saved limits.</Callout>}
    {data.state.cancel_requested && !data.active && <Callout tone="warn" title="Cancellation is saved">Resume before starting more work.</Callout>}
    {/* The page transform would pin a fixed alert to the page instead of the screen. */}
    {error && createPortal(<div role="alert" className={`${styles.error} ${styles.toast}`}><span>{error}</span>
      <Button variant="ghost" onClick={() => setError("")}>Dismiss</Button></div>, document.body)}
    <nav className={styles.sectionNav} aria-label="Investigation sections"><a href="#results">Results</a><a href="#run-checks">Run tests</a><a href="#compare-fix">Compare a fix</a><a href="#activity">Activity</a></nav>
    <div id="results"><Findings data={data} busy={busy} act={act} />{data.reductions.length > 0 && <Reductions reductions={data.reductions} />}</div>
    <div id="run-checks"><Disclosure title={data.experimentsUsed ? "Run more fault tests" : "Run your first fault tests"} initiallyOpen={!data.experimentsUsed || Boolean(data.active)}
      description="Run the saved checks locally, or explicitly allow Nemotron to propose new faults."><Controls data={data} busy={busy} act={act} /></Disclosure></div>
    <div id="compare-fix"><Remedies data={data} busy={busy} act={act} /></div>
    <div id="activity"><Disclosure title="Activity and proposed tests" description="The saved timeline, AI request usage, rejected proposals, and technical setup.">
      <Timeline data={data} /><Proposals proposals={data.proposals} />
      <p className={styles.footnote}>Model setup: {data.context}. Failure patterns: {data.discoveryFamilies.join(", ") || "None"}. Criterion: {data.criterion?.candidate ?? "Not set"}.</p>
    </Disclosure></div>
    <Panel title="Save and share results" description="Download the measured evidence and the settings needed to interpret it."><div className={styles.actions}>
      <Button variant="secondary" onClick={() => exportEvidence("export")} loading={busy === "export"}><Download size={16} aria-hidden="true" />Export evidence</Button>
      <Button variant="ghost" onClick={() => exportEvidence("public")} loading={busy === "public"}><Download size={16} aria-hidden="true" />Public evidence</Button>
    </div><p className={styles.footnote}>Full evidence includes your concern. Public evidence leaves out the concern, equipment IDs and raw readings.</p></Panel>
  </>;
}

type Act = (label: string, action: () => Promise<unknown>) => Promise<void>;

function Controls({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const [allow, setAllow] = useState(false);
  const [calls, setCalls] = useState("4");
  const [tokens, setTokens] = useState("32768");
  const controller = data.controller as { callsUsed?: number; reservedCompletionTokens?: number; reportedCompletionTokens?: number } | null;
  const locked = Boolean(data.active) || data.state.cancel_requested || Boolean(busy);
  const validCalls = Number.isInteger(Number(calls)) && Number(calls) >= 1 && Number(calls) <= 64;
  const validTokens = Number.isInteger(Number(tokens)) && Number(tokens) >= 1 && Number(tokens) <= 1000000;
  if (data.active) return <Panel title="Running" aside={<Button variant="danger" onClick={() => act("cancel", () => investigations.cancel(data.id))} loading={busy === "cancel"}>Cancel</Button>}>
    <p>Each finished test is added to Results. Cancelling stops at the next safe point; saved results stay available.</p>
  </Panel>;
  return <Panel title="Run experiments" aside={data.state.cancel_requested ? <Button onClick={() => act("resume", () => investigations.resume(data.id))} loading={busy === "resume"}>Resume</Button> : undefined}>
    <div className={styles.stack}>
      <div className={styles.actions}>
        <Button disabled={locked} loading={busy === "run"} onClick={() => act("run", () => investigations.start(data.id, { requestId: requestId(), mode: "run" }))}>Run saved proposals</Button>
        <span className={styles.footnote}>Test the faults already saved in this investigation. Runs locally, with no AI request.</span>
      </div>
      <fieldset className={styles.preview}>
        <legend>Nemotron search</legend>
        <p>Let Nemotron choose the next sensor fault, inspect its measured result, and decide what to test next.</p>
        <Disclosure title="What is sent to Nebius"><p>Your concern, channel aliases with reviewed descriptions, fault bounds, baseline performance and aggregate matched results are sent for each call.</p>
          <p>Sensor names, raw readings, equipment IDs, fitted models and keys are excluded. Workspace AI permission is also required.</p></Disclosure>
        <div className={styles.fields}>
          <Input label="Provider calls" description="Maximum requests to Nemotron for this run." type="number" min={1} max={64} value={calls} onChange={event => setCalls(event.target.value)} />
          <Input label="Completion token ceiling" description="Maximum reserved reasoning and answer tokens, not actual usage or a price." type="number" min={1} max={1000000} value={tokens} onChange={event => setTokens(event.target.value)} />
        </div>
        {(!validCalls || !validTokens) && <p role="alert" className={styles.error}>Use 1 to 64 provider calls and 1 to 1,000,000 completion tokens, as whole numbers.</p>}
        <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow sending this information to Nebius for this run</label>
        <div className={styles.actions}>
          <Button variant="primary" disabled={!allow || locked || !validCalls || !validTokens} loading={busy === "agent"} onClick={() => act("agent", () => investigations.start(data.id, { requestId: requestId(), mode: "agent", allowProvider: true, maxProviderCalls: Number(calls), maxCompletionTokens: Number(tokens) }))}>Start Nemotron search</Button>
          {controller && <span className={styles.footnote}>Calls used {controller.callsUsed ?? 0}; reserved {controller.reservedCompletionTokens ?? 0} tokens; reported {controller.reportedCompletionTokens ?? 0}.</span>}
        </div>
      </fieldset>
    </div>
  </Panel>;
}

function Findings({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const measured = data.findings.filter(item => item.attempt_id).sort((a, b) => Number(b.status === "measured_failure") - Number(a.status === "measured_failure"));
  if (!data.criterion) return <Panel title="Findings"><p>This investigation has no finding criterion, so results are not classified.</p></Panel>;
  return <Panel title="Findings" description="Measured failures come first. Every comparison uses the same model and matched development histories.">
    {measured.length === 0 ? <div className={styles.empty}><FlaskConical size={23} aria-hidden="true" /><h3>No results yet</h3><p>Run the initial checks or start a Nemotron search. Finished fault tests will appear here.</p><a href="#run-checks">Choose how to run tests</a></div> : <div className={styles.resultList}>
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
      <Badge tone={chosen ? "info" : "neutral"}>{chosen ? "Chosen by Nemotron" : "Supplied case"}</Badge><h3>{caseTitle(proposal?.scenario)}</h3></header>
    <Disclosure title={finding.status === "no_measured_failure" ? "View test details" : "Measured result and next steps"} initiallyOpen={finding.status !== "no_measured_failure"}
      description={finding.status === "no_measured_failure" ? `Useful warnings ${percent(finding.clean_detection)} to ${percent(finding.faulted_detection)}. ${finding.evaluated_histories ?? 0} of ${finding.expected_histories ?? 0} histories evaluated.` : undefined}>
    {finding.status === "execution_error" ? <p>{finding.reasons?.[0]}</p> : <>
      <div className={styles.comparisonGrid}><WarningComparison before={finding.clean_detection} after={finding.faulted_detection} />
        <WarningComparison label="Early alarm burden" before={finding.clean_burden} after={finding.faulted_burden} lowerIsBetter /></div>
      <p className={styles.coverage}><strong>{finding.evaluated_histories ?? 0} of {finding.expected_histories ?? 0}</strong> machine histories evaluated{partial ? ". Partial coverage limits this conclusion." : ". Full coverage for this test."}</p>
      {unscored && <p><strong>Why this was not scored as a finding:</strong></p>}
      {finding.reasons?.map(reason => <p key={reason} className={styles.reason}>{reason}</p>)}
      {finding.effects?.map(effect => <p key={effect.kind}>{effect.kind.replace(/_/g, " ")}: {histories(effect.histories.length)}</p>)}
      <Disclosure title="Timing, affected histories, and assumptions"><p className={styles.footnote}>{describeCase(proposal?.scenario)}</p>
        {(finding.support?.length ?? 0) > 0 && <details><summary>{histories(finding.support?.length ?? 0)} with recorded changes</summary>
        <div className="table-scroll"><table><thead><tr><th>History</th><th>Clean</th><th>Faulted</th><th className="num">Lead</th></tr></thead>
          <tbody>{finding.support?.map(row => <tr key={row.equipment_id}><td>{row.equipment_id}</td><td>{row.clean}</td><td>{row.faulted}</td>
            <td className="num">{row.clean_lead ?? "—"} → {row.faulted_lead ?? "—"}</td></tr>)}</tbody></table></div>
      </details>}
      {(finding.assumptions?.length ?? 0) > 0 && <details><summary>Profile assumptions</summary><ul>{finding.assumptions?.map(item => <li key={item}>{item}</li>)}</ul></details>}
      </Disclosure>
      <div className={styles.actions}>
        {finding.status === "measured_failure" && <Button disabled={Boolean(data.active) || Boolean(busy) || data.state.cancel_requested} loading={busy === `reduce-${attempt}`}
          onClick={() => act(`reduce-${attempt}`, () => investigations.reduce(data.id, { requestId: requestId(), attempt, maxExperiments: 16 }))}>Reduce</Button>}
        <Button variant="secondary" disabled={Boolean(busy)} loading={busy === `replay-${attempt}`} onClick={() => act(`replay-${attempt}`, async () => {
          const check = await investigations.replay(data.id, attempt);
          setReplay(check.matches ? "Replay reproduced this result exactly." : "Replay did not reproduce this result.");
        })}>Replay</Button>
        {replay && <span role="status" className={styles.footnote}>{replay}</span>}
      </div>
      <FaultResearch finding={finding} data={data} busy={busy} act={act} />
    </>}
    </Disclosure>
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
    <div className={styles.heading}><strong>Fault research</strong><Badge tone={report.status === "completed" ? "info" : "neutral"}>{report.status.replace(/_/g, " ")}</Badge></div>
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
    <Button variant="ghost" className={styles.researchToggle} onClick={() => setOpen(!open)} aria-expanded={open}>Research this fault</Button>
    {open && <fieldset className={styles.preview}><legend>Research this fault</legend>
      <p>Tavily receives this search:</p><p>{query}</p>
      <p>Nemotron receives up to three source excerpts and aliased aggregate experiment results. No raw readings, sensor names, equipment IDs or private concern are sent.</p>
      <p>One search and one Nemotron request, with at most 5,120 completion tokens. References are unverified context and do not change your measured findings. Workspace AI permission is also required.</p>
      <label className={styles.check}><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow Tavily search and Nemotron research for this fault</label>
      <Button disabled={!allow || Boolean(data.active) || Boolean(busy) || data.state.cancel_requested} loading={busy === `research-${attempt}`}
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
  const operations: Record<string, string> = { run: "saved fault tests", agent: "Nemotron search", reduce: "fault simplification", remedy: "fix comparison", research: "fault research" };
  return <Panel title="Timeline">
    <ol className={styles.timeline}>
      {[...data.events].reverse().map(event => {
        const [kind, operation] = event.kind.split(":");
        const text = operation ? `${kind === "started" ? "Started" : kind === "finished" ? "Finished" : "Failed"} ${operations[operation] ?? operation}` : eventLabels[event.kind] ?? event.kind;
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
      <div className="table-scroll"><table className={styles.proposalsTable} aria-label="Investigation proposals"><thead><tr><th className="num">#</th><th>Case</th><th>Status</th><th>Hypothesis or reason</th></tr></thead>
        <tbody>{proposals.map(item => {
          const hypothesis = item.hypothesis as { suspected?: string; supportIf?: string; weakenIf?: string } | null;
          return <tr key={item.id}><td className="num">{item.sequence}</td><td><strong>{caseTitle(item.scenario)}</strong><div className={styles.reason}>{describeCase(item.scenario)}</div></td>
            <td><Badge tone={item.status === "rejected" ? "warn" : "neutral"}>{item.status.replace(/_/g, " ")}</Badge>{item.rejection ? <div className={styles.reason}>{item.rejection}</div> : null}</td>
            <td>{hypothesis ? <><strong>Hypothesis:</strong> {hypothesis.suspected} <span className={styles.footnote}>Supported if {hypothesis.supportIf}; weakened if {hypothesis.weakenIf}</span></> : item.reason}</td></tr>;
        })}</tbody></table></div>
    </StateBlock>
  </Panel>;
}

function Reductions({ reductions }: { reductions: Record<string, unknown>[] }) {
  return <Panel title="Simplified failures" description="Remove faults or lower their severity, rerunning each change to check that the failure still occurs.">
    <div className={styles.stack}>{reductions.map(item => {
      const reduction = item as { id: string; status: string; experiments: number; claims: string[]; original: Record<string, unknown>; final: Record<string, unknown> | null; steps: unknown[] };
      return <article key={reduction.id} className={styles.finding}>
        <header><Badge tone={reduction.status === "complete" ? "ok" : "warn"}>{reduction.status.replace(/_/g, " ")}</Badge><strong>{reduction.experiments} additional tests</strong></header>
        <div className={styles.reductionPath}><div><span>Original fault</span><strong>{caseTitle(reduction.original)}</strong><p className={styles.footnote}>{describeCase(reduction.original)}</p></div><ArrowRight size={20} aria-hidden="true" />
          <div><span>After simplification</span><strong>{caseTitle(reduction.final ?? reduction.original)}</strong><p className={styles.footnote}>{describeCase(reduction.final ?? reduction.original)}</p></div></div>
        <p className={styles.footnote}>{reduction.steps.length} checked steps. This is a bounded search, not proof of the smallest possible failure.</p>
        <Disclosure title="Reduction evidence and exact settings"><p>{describeCase(reduction.original)}</p><p>{describeCase(reduction.final ?? reduction.original)}</p>
          <ul>{reduction.claims.map(claim => <li key={claim}>{claim}</li>)}</ul></Disclosure>
      </article>;
    })}</div>
  </Panel>;
}

function Remedies({ data, busy, act }: { data: InvestigationView; busy: string; act: Act }) {
  const [kind, setKind] = useState<"threshold" | "augmented">("threshold");
  const [threshold, setThreshold] = useState("0.5");
  const [approve, setApprove] = useState(false);
  const ready = data.discoveries > 0 || data.reductions.length > 0;
  const reports = useMemo(() => data.remedies as { id: string; kind: string; threshold: number | null; improved: number; degraded: number; stillFailing?: number; meetsCriteria: boolean;
    clean: { original: { detection: number; alarmBurden: number | null }; remedy: { detection: number; alarmBurden: number | null } }; note: string }[], [data.remedies]);
  const validThreshold = threshold.trim() !== "" && Number.isFinite(Number(threshold)) && Number(threshold) >= 0 && Number(threshold) <= 1;
  return <Panel title="Compare a fix" description="Test a warning threshold or retrained model against discovered failures and previously passing cases. Deployed models are unchanged.">
    <div className={styles.stack}>
      {ready ? <form className={styles.form} onSubmit={event => {
        event.preventDefault();
        if (kind === "threshold" && !validThreshold) return;
        void act("remedy", () => investigations.remedy(data.id, { requestId: requestId(), kind, threshold: kind === "threshold" ? Number(threshold) : null, approveTraining: approve }));
      }}><div className={styles.fields}>
        <Select label="Remedy" value={kind} onValueChange={value => setKind(value as "threshold" | "augmented")} options={[{ value: "threshold", label: "Explicit warning threshold" }, { value: "augmented", label: "Augmented retraining" }]} />
        {kind === "threshold" ? <Input label="Threshold" description="A lower threshold can recover warnings but increase early alarms." required type="number" min={0} max={1} step="any" value={threshold} onChange={event => setThreshold(event.target.value)} />
          : <label className={styles.check}><input type="checkbox" checked={approve} onChange={event => setApprove(event.target.checked)} />Approve development-only retraining</label>}
      </div><div className={styles.actions}><Button type="submit" disabled={Boolean(data.active) || Boolean(busy) || data.state.cancel_requested || (kind === "augmented" ? !approve : !validThreshold)} loading={busy === "remedy"}>Compare remedy</Button></div></form>
        : <p>Once a test reveals a measured failure, compare a fix here and check what it costs elsewhere.</p>}
      {reports.map(report => <article key={report.id} className={styles.finding}>
        <header><Badge tone={report.meetsCriteria ? "ok" : "bad"}>{report.meetsCriteria ? "Comparison criteria met" : "Comparison criteria not met"}</Badge>
          <strong>{report.kind === "threshold" ? `Threshold ${report.threshold}` : "Augmented retraining"}</strong></header>
        <dl className={styles.metrics}>
          <div><dt>Improved cases</dt><dd>{report.improved}</dd></div><div><dt>Degraded cases</dt><dd>{report.degraded}</dd></div>
          <div><dt>Still failing</dt><dd>{report.stillFailing ?? "Not recorded"}</dd></div>
        </dl>
        <div className={styles.comparisonGrid}><WarningComparison before={report.clean.original.detection} after={report.clean.remedy.detection} beforeLabel="Original model" afterLabel="With proposed fix" label="Warnings without sensor faults" />
          <WarningComparison before={report.clean.original.alarmBurden} after={report.clean.remedy.alarmBurden} beforeLabel="Original model" afterLabel="With proposed fix" label="Early alarm burden" lowerIsBetter /></div>
        <p className={styles.footnote}>{report.note}</p>
        <p className={styles.footnote}>Comparison criteria check baseline warnings, early alarms, and new failures. Existing failures can remain even when the criteria are met.</p>
      </article>)}
    </div>
  </Panel>;
}
