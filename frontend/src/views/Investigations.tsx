import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, FlaskConical } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";
import { Select } from "@/registry/components/select/select";
import { api, investigations } from "../api/client";
import type { ContextInfo, Finding, RecordedInvestigation } from "../api/types";
import { Badge, Button, Callout, Panel, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { candidateLabel, percent } from "../format";
import { errorText, findingTones, stops } from "../components/investigations/cases";
import { ContextSetup } from "../components/investigations/ContextSetup";
import { Disclosure } from "../components/investigations/Disclosure";
import { WarningComparison } from "../components/investigations/WarningComparison";
import styles from "./investigations.module.css";

export function Investigations() {
  const health = useApi(() => api.health(), []);
  return <StateBlock loading={health.loading} error={health.error}>
    <header className="page-head"><h1>Fault investigations</h1><p>Find the sensor faults that make a model miss useful warnings, then test a fix.</p></header>
    {health.data?.mode === "full" ? <Workspace /> : <>
      <Panel title="Run investigations locally"><p>This site cannot start investigations or call Nemotron. These are saved runs: opening one runs nothing.</p></Panel>
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

const recordTitles: Record<string, string> = { "nemotron-live-recorded": "Nemotron search", "compound-demo-recorded": "A combined sensor failure", "fresh-validation-recorded": "Checking a fix on fresh data", "synthetic-recorded": "Initial sensor checks",
  "nemotron-live-default": "Nemotron search on the default model", "nemotron-live-browser": "A sensor failure proposed by Nemotron", "nemotron-live-demo": "A supplied sensor failure" };

function Recorded() {
  const recorded = useApi(() => investigations.recorded(), []);
  return <StateBlock loading={recorded.loading} error={recorded.error} empty={recorded.data?.length === 0}>
    {recorded.data?.map(item => <RecordedRun key={item.name} item={item} />)}
  </StateBlock>;
}

function RecordedRun({ item }: { item: RecordedInvestigation }) {
  const evidence = item.evidence as unknown as RecordedEvidence;
  const controller = evidence.controller;
  const focus = evidence.experiments.find(row => row.status === "measured_failure" && row.chosenBy === "nemotron")
    ?? evidence.experiments.find(row => row.status === "measured_failure") ?? evidence.experiments[0];
  const failures = evidence.experiments.filter(row => row.status === "measured_failure").length;
  const reduced = evidence.reductions.length;
  const steps = [
    ...(reduced ? [{ label: `Simplified ${reduced} ${reduced === 1 ? "failure" : "failures"}`, text: [...new Set(evidence.reductions.map(reduction => reduction.status))].join(", ") }] : []),
    ...evidence.remedies.map(remedy => ({ label: `Fix at threshold ${remedy.threshold}:`, text: `${remedy.improved} improved, ${remedy.degraded} degraded${remedy.stillFailing !== undefined ? `, ${remedy.stillFailing} still failing` : ""}. Development only.` })),
    ...(evidence.validations ?? []).map(validation => {
      const failing = validation.cases.filter(row => (row.remedy ?? row.original).status === "measured_failure").length;
      return { label: `Validation on ${validation.freshHistories} fresh histories (${validation.status}):`, text: `${failing} of ${validation.cases.length} ${validation.cases.length === 1 ? "case" : "cases"} fail on fresh data.` };
    })
  ];
  return <Panel title={recordTitles[item.name] ?? item.name.replace(/[-_]/g, " ")} aside={<Badge tone="neutral">Recorded, not live</Badge>}>
    <div className={styles.stack}>
      {evidence.demonstration && <Callout tone="warn" title="Demonstration setting">{evidence.demonstration.note.replace(/^Demonstration setting:\s*(\w)/, (_, first: string) => first.toUpperCase())}</Callout>}
      <div className={styles.recordSummary}><span><strong>{evidence.experiments.length}</strong> saved tests</span><span><strong>{failures}</strong> measured {failures === 1 ? "failure" : "failures"}</span>
        <span>{controller ? `${controller.callsUsed} Nemotron ${controller.callsUsed === 1 ? "call" : "calls"}` : "Cases supplied by the builder"}</span></div>
      {focus && <div className={styles.stack}><div className={styles.meta}><h3>{focus.status === "measured_failure" ? "A fault that cost useful warnings" : findingTones[focus.status][0]}</h3>
        <Badge tone={findingTones[focus.status][1]}>{findingTones[focus.status][0]}</Badge></div>
        <WarningComparison before={focus.cleanDetection} after={focus.faultedDetection} />
        <p className={styles.footnote}>{focus.evaluatedHistories} of {focus.expectedHistories} machine histories evaluated. {focus.chosenBy === "nemotron" ? "This case was proposed by Nemotron." : "This case was supplied by the builder."}</p></div>}
      {steps.length > 0 && <ol className={styles.storyline}>{steps.map((step, index) => <li key={index}><strong>{step.label}</strong> <span>{step.text}</span></li>)}</ol>}
      <Disclosure title={`All recorded tests (${evidence.experiments.length})`}>
        <div className="table-scroll"><table aria-label={`Recorded experiments: ${item.name}`}><thead><tr><th>Result</th><th>Case family</th><th>Chosen by</th><th>Status</th>
          <th className="num">Coverage</th><th className="num">Useful warnings</th></tr></thead>
          <tbody>{evidence.experiments.map(row => <tr key={row.ref}><td>{row.ref}</td><td>{row.family}</td><td>{row.chosenBy === "nemotron" ? "Nemotron" : "Supplied"}</td>
            <td><Badge tone={findingTones[row.status][1]}>{findingTones[row.status][0]}</Badge></td><td className="num">{row.evaluatedHistories} / {row.expectedHistories}</td>
            <td className="num">{percent(row.cleanDetection)} → {percent(row.faultedDetection)}</td></tr>)}</tbody></table></div>
        {evidence.reductions.map((reduction, index) => <p key={index} className={styles.footnote}>Simplified ({reduction.status}): {reduction.family}. {reduction.claims.join(" ")}</p>)}
        {(evidence.validations ?? []).map((validation, index) => <p key={index} className={styles.footnote}>Fresh validation: {validation.cases.map(row => `${row.label} ${row.original.status.replace(/_/g, " ")}${row.remedy ? ` (with fix: ${row.remedy.status.replace(/_/g, " ")})` : ""}`).join("; ")}.</p>)}
        <p>{controller ? `Nemotron (${controller.model}, ${controller.prompt}) used ${controller.callsUsed} ${controller.callsUsed === 1 ? "call" : "calls"}: ${controller.reportedCompletionTokens} reported completion tokens within a reserved ceiling of ${controller.reservedCompletionTokens}.`
          : "No Nemotron calls; every case was supplied."}</p>
        <p className={styles.footnote}>Recorded at {evidence.generatedAt}. Record: {item.name}. Integrity digest: {evidence.digest}.</p>
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
  const setup = <ContextSetup ready={Boolean(first)} onReady={contexts.reload} />;
  return <>
    {!first && setup}
    {available && contexts.error && <Callout tone="warn" title="Could not refresh model setups">Your current form is kept. <Button variant="ghost" onClick={contexts.reload}>Refresh model setups</Button></Callout>}
    <StateBlock loading={!available && contexts.loading} error={available ? null : contexts.error}>
      {available && first && <CreateForm contexts={available} initial={first} />}
    </StateBlock>
    <Panel title="Saved investigations" tight>
      <StateBlock loading={saved.loading} error={saved.error}>
        {saved.data?.length === 0 ? <div className={styles.empty}><FlaskConical size={23} aria-hidden="true" /><h3>No investigations yet</h3><p>Investigations you create are saved here.</p></div>
          : <ul className={styles.savedList}>{saved.data?.map(item => <li key={item.id}>
            <Link to={`/investigations/${item.id}`} title={item.objective}><strong>{item.objective}</strong><span>{item.experimentsUsed} of {item.maxExperiments} tests used <span aria-hidden="true">·</span> {item.discoveries} measured {item.discoveries === 1 ? "failure" : "failures"}</span></Link>
            {item.active ? <Badge tone="info">Running {item.active}</Badge> : item.stopReason ? <Badge tone={stops[item.stopReason]?.[1]}>{stops[item.stopReason]?.[0] ?? item.stopReason}</Badge> : <Badge>Not started</Badge>}
            <ArrowRight size={16} aria-hidden="true" />
          </li>)}</ul>}
      </StateBlock>
    </Panel>
    {first && setup}
  </>;
}

const setupLabel = (name: string) => name.startsWith("demo-fragile") ? `Sample with a fragile warning threshold (${name.slice(-6)})` : name.startsWith("synthetic-") ? `Rotating machine sample (${name.slice(-6)})` : name;

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
  const clean = context.clean[target];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const created = await investigations.create({ context: context.name, objective, maxExperiments: Number(experiments), seed: Number(seed), criterion: { candidate: target } });
      navigate(`/investigations/${created.id}`);
    } catch (failure) { setError(errorText(failure)); setBusy(false); }
  }

  return <Panel title="New investigation">
    <form className={styles.form} onSubmit={submit}>
      <Textarea label="Concern" value={objective} maxLength={2000} rows={2} onChange={event => setObjective(event.target.value)} />
      <div className={styles.fields}>
        <Select label="Model under test" value={target} onValueChange={value => setCandidate(String(value))} options={models.map(name => {
          const [family, ...config] = name.split("/");
          return { value: name, label: candidateLabel(family ?? name, config.join("/") || undefined) };
        })} />
        <div className={styles.baseline}><span>Before sensor faults</span><dl aria-label="Performance before sensor faults">
          <div><dt>Useful warnings</dt><dd>{percent(clean?.detection)}</dd></div><div><dt>Early alarms</dt><dd>{percent(clean?.alarmBurden, 1)}</dd></div>
          <div><dt>Histories</dt><dd>{clean?.histories}</dd></div></dl></div>
      </div>
      {target.startsWith("age_baseline/") && <p className={styles.footnote}>The age baseline uses elapsed age, not sensor readings. Select a sensor-based model to investigate the effect of sensor faults.</p>}
      <Disclosure title="More options" description={`${setupLabel(context.name)} · up to ${experiments || "?"} tests · ${seed || "0"} initial checks`}>
        <Select label="Model setup" value={context.name} onValueChange={value => setContextName(String(value))} options={contexts.map(item => ({ value: item.name, label: setupLabel(item.name) }))} />
        <div className={styles.fields}>
          <Input label="Experiment budget" description="Maximum fault tests" type="number" required min={1} max={128} value={experiments} onChange={event => setExperiments(event.target.value)} />
          <Input label="Initial checks" description="Known single-sensor faults tested first, from the budget" type="number" required min={0} max={Math.min(12, Number(experiments) || 12)} value={seed} onChange={event => setSeed(event.target.value)} />
        </div>
        <div className="table-scroll"><table aria-label="Clean performance"><thead><tr><th>Model</th><th className="num">Threshold</th><th className="num">Useful warnings</th><th className="num">Early alarm burden</th><th className="num">Histories</th></tr></thead>
          <tbody>{models.map(name => <tr key={name}><td>{name}</td><td className="num">{context.thresholds[name]}</td><td className="num">{percent(context.clean[name]?.detection)}</td>
            <td className="num">{percent(context.clean[name]?.alarmBurden, 1)}</td><td className="num">{context.clean[name]?.histories}</td></tr>)}</tbody></table></div>
        <p className={styles.footnote}>Fault profile: {context.profile ?? "None"}. Its relationships are declared assumptions, not proof of physical causes. Performance is measured on development histories before any sensor fault.</p>
      </Disclosure>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      <div className={styles.actions}><Button type="submit" variant="primary" loading={busy}>Create investigation</Button></div>
    </form>
  </Panel>;
}
