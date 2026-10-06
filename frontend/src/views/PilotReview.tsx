import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, Download } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";
import { RadioGroup } from "@/components/arc/radio-group/radio-group";
import { api, ApiError, downloadEvidence, evidenceApi, experiments, pilots } from "../api/client";
import type { ExperimentRecord, FaultScenario, PilotAgreementCreate, PilotAgreementRecord, PilotBrief, PilotDecision, PilotOutcomeCreate, PilotOutcomeRecord } from "../api/types";
import { Badge, Button, Panel, StateBlock } from "../components/Chrome";
import { ValidationPanel } from "../components/ValidationPanel";
import { useApi } from "../hooks/useApi";
import { candidateLabel, percent } from "../format";
import styles from "./pilot-review.module.css";

const decisions: Record<PilotDecision, string> = {
  supervised_trial: "Consider a supervised site trial", revise_model: "Revise the model",
  collect_data: "Collect more data", stop: "Do not proceed"
};
const errorText = (error: unknown) => error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Could not save. Try again.";
const modelName = (key: string) => { const [kind = "", configuration] = key.split("/"); return candidateLabel(kind, configuration); };

export function PilotReview() {
  const { experimentId } = useParams();
  const health = useApi(() => api.health(), []);
  return <StateBlock loading={health.loading} error={health.error}>
    {health.data?.can_review_pilot && experimentId ? <PilotWorkspace id={experimentId} /> : <>
      <header className="page-head"><h1>Equipment pilot</h1></header>
      <Panel title="Run the pilot locally"><p>Equipment data, model freezing and engineer reviews stay in your local workspace.</p><Link to="/comparison">Explore the recorded results</Link></Panel>
    </>}
  </StateBlock>;
}

function PilotWorkspace({ id }: { id: string }) {
  const evidence = useMemo(() => evidenceApi(id), [id]);
  const pilot = useApi(() => pilots.get(id), [id]);
  const run = useApi(() => experiments.get(id), [id]);
  const selection = useApi(() => evidence.selection(), [id]);
  const final = useApi(() => evidence.finalEvaluation(), [id, pilot.data?.phase]);
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState(false);
  const [error, setError] = useState("");
  const phase = pilot.data?.phase ?? "agreement";
  const current = phase === "agreement" ? 0 : phase === "evaluation" ? 1 : 2;
  const selected = selection.data?.recommended;
  const finalModel = final.data?.selection?.ranked[0];
  const synthetic = run.data?.source === "synthetic" || pilot.data?.agreement?.brief.data_classification === "simulated";
  const sourceLabel = synthetic ? "Simulated pilot" : pilot.data?.agreement?.brief.data_classification === "field" ? "Field records (declared)" : "Uploaded data";

  async function exportReview() {
    setExporting(true); setError(""); setExported(false);
    try {
      await downloadEvidence(evidenceApi(id, undefined, "holdout").exportUrl, `sidekick-pilot-${id.slice(0, 8)}.zip`);
      setExported(true);
    } catch (failure) { setError(errorText(failure)); }
    finally { setExporting(false); }
  }

  return <>
    <header className={`page-head ${styles.heading}`}><h1>Equipment pilot</h1><Badge>{sourceLabel}</Badge></header>
    <ol className={styles.steps} aria-label="Pilot progress" aria-live="polite">
      {["Agree the test", "Check reserved data", "Record the decision"].map((label, index) => <li key={label} aria-current={index === current ? "step" : undefined}>
        {index < current || phase === "complete" ? <Check size={16} aria-label="Complete" /> : <span>{index + 1}.</span>}{label}
      </li>)}
    </ol>
    <StateBlock loading={pilot.loading || run.loading || selection.loading} error={pilot.error || run.error || selection.error}>
      {pilot.data && run.data && <>
        {pilot.data.agreement && <AgreementSummary agreement={pilot.data.agreement} />}
        {phase === "agreement" && (pilot.data.agreement_blocked ? <Panel title="A new experiment is needed">
          <p className={styles.blocked}>{pilot.data.agreement_blocked}</p><Link className="button" to={`/new?source=${run.data.source === "synthetic" ? "sample" : "upload"}`}>Set up a new experiment</Link>
        </Panel> : <AgreementForm id={id} run={run.data} onSaved={pilot.reload} />)}
        {phase === "evaluation" && pilot.data.review_blocked && final.data?.available ? <Panel title="Check the pilot evidence"><p>{pilot.data.review_blocked}</p></Panel> : phase === "evaluation" && <>
          <ValidationPanel experimentId={id} qualifies={Boolean(selected?.qualifies)} recommendation={selected} onCompleted={pilot.reload} />
          <p className={styles.footnote}>The model and test stay fixed. Reserved scoring can run once.</p>
        </>}
        {(phase === "review" || phase === "complete") && <>
          <Panel title="Reserved evaluation" aside={<Badge tone={pilot.data.final_qualifies ? "ok" : "bad"}>{pilot.data.final_qualifies ? "Meets test limits" : "Below test limits"}</Badge>}>
            <StateBlock loading={final.loading} error={final.error}>
              {finalModel && <div className={styles.stack}>
                <dl className={styles.summary}>
                  <div><dt>Healthy sensors: warnings in time</dt><dd>{finalModel.clean.detected} / {finalModel.clean.engines}</dd></div>
                  <div><dt>Weakest fault: warnings in time</dt><dd>{finalModel.worst_metrics ? `${finalModel.worst_metrics.detected} / ${finalModel.worst_metrics.engines}` : percent(finalModel.worst_detection_required)}</dd></div>
                  <div><dt>Highest early-alarm burden</dt><dd>{percent(finalModel.worst_burden_required, 1)}</dd></div>
                </dl>
                <Link to={`/experiments/${id}/comparison?partition=holdout`}>Inspect final results</Link>
              </div>}
            </StateBlock>
          </Panel>
          {pilot.data.outcome ? <OutcomeSummary outcome={pilot.data.outcome} synthetic={synthetic} /> : <ReviewForm id={id} reviewer={pilot.data.agreement?.brief.reviewing_engineer ?? ""} allowsTrial={Boolean(pilot.data.final_qualifies) && pilot.data.agreement?.data_source === "upload" && pilot.data.agreement.brief.data_classification === "field"} onSaved={pilot.reload} />}
        </>}
      </>}
    </StateBlock>
    {phase === "complete" && <div className={styles.actions}>
      <Button variant="primary" loading={exporting} onClick={exportReview}><Download size={15} aria-hidden="true" />{exported ? "Download pilot evidence again" : "Download pilot evidence"}</Button>
      {exported && <span role="status">Download started</span>}
    </div>}
    {error && <p role="alert" className="state error">{error}</p>}
    <p className={styles.footnote}>A test result supports review. It is not deployment approval.</p>
  </>;
}

function AgreementForm({ id, run, onSaved }: { id: string; run: ExperimentRecord; onSaved: () => void }) {
  const [brief, setBrief] = useState<PilotBrief>({ ...run.pilot_brief, data_classification: run.source === "synthetic" ? "simulated" : run.pilot_brief?.data_classification ?? "unverified" });
  const [checks, setChecks] = useState({ single_family_confirmed: false, failure_labels_checked: false, representative_data_confirmed: false, protocol_agreed: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const synthetic = run.source === "synthetic";
  const required = [brief.equipment_family, brief.reviewing_engineer, brief.current_procedure, brief.intended_decision, brief.success_measure];
  const ready = required.every(value => value?.trim()) && brief.data_classification !== "unverified" && Object.values(checks).every(Boolean);
  const edit = (field: keyof PilotBrief, value: string) => setBrief(previous => ({ ...previous, [field]: value }));
  const labels: Record<keyof typeof checks, string> = {
    single_family_confirmed: "One equipment family is represented",
    failure_labels_checked: "Failure labels and column mapping are checked",
    representative_data_confirmed: synthetic ? "Data covers the intended simulated conditions" : "Data covers the intended operating conditions",
    protocol_agreed: "Reviewer agrees the warning window, faults and limits"
  };
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await pilots.agree(id, { brief, ...checks } satisfies PilotAgreementCreate); onSaved(); }
    catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <Panel title="Agree the pilot" description="Record the scope before reserved scoring.">
    <form className={styles.form} onSubmit={save}>
      <fieldset disabled={busy} className={styles.checks}>
        <div className={styles.fields}>
          <Input label="Equipment family" required maxLength={200} value={brief.equipment_family ?? ""} onChange={e => edit("equipment_family", e.target.value)} />
          <Input label="Reviewing engineer" required maxLength={200} value={brief.reviewing_engineer ?? ""} onChange={e => edit("reviewing_engineer", e.target.value)} />
        </div>
      </fieldset>
      {!synthetic && <fieldset disabled={busy} className={styles.checks}><RadioGroup label="Data origin (user declared)" value={brief.data_classification ?? "unverified"} onValueChange={value => edit("data_classification", value)} options={[{ value: "field", label: "Field records" }, { value: "simulated", label: "Simulated records" }]} /></fieldset>}
      <div className={styles.fields}>
        <Textarea label="Current review procedure" required disabled={busy} rows={2} maxLength={2000} value={brief.current_procedure ?? ""} onChange={e => edit("current_procedure", e.target.value)} />
        <Textarea label="Decision this test supports" required disabled={busy} rows={2} maxLength={2000} value={brief.intended_decision ?? ""} onChange={e => edit("intended_decision", e.target.value)} />
      </div>
      <Input label="Success measure" required disabled={busy} maxLength={1000} value={brief.success_measure ?? ""} onChange={e => edit("success_measure", e.target.value)} />
      <ProtocolSummary run={run} />
      <fieldset disabled={busy} className={styles.checks}><legend>Reviewer checks</legend>
        {(Object.keys(checks) as Array<keyof typeof checks>).map(key => <label key={key}><input type="checkbox" checked={checks[key]} onChange={e => setChecks(previous => ({ ...previous, [key]: e.target.checked }))} />{labels[key]}</label>)}
      </fieldset>
      {error && <p className="state error" role="alert">{error}</p>}
      <div className={styles.actions}><Button type="submit" variant="primary" loading={busy} disabled={!ready}>Save pilot agreement</Button></div>
      <p className={styles.footnote}>Saved once for this experiment. Checks are reviewer declarations.{synthetic ? " Simulated data cannot establish field performance." : ""}</p>
    </form>
  </Panel>;
}

function ProtocolSummary({ run }: { run: ExperimentRecord }) {
  const config = run.config;
  const cases = config.fault_scenarios as FaultScenario[] | undefined;
  return <div className={styles.stack}>
    <dl className={styles.summary}>
      <div><dt>Useful warning window</dt><dd>{String(config.min_useful_lead)} to {String(config.horizon_cycles)} cycles</dd></div>
      <div><dt>Minimum warnings in time</dt><dd>{percent(Number(config.min_detection_fraction))}</dd></div>
      <div><dt>Maximum early-alarm burden</dt><dd>{percent(Number(config.max_early_alarm_burden))}</dd></div>
    </dl>
    <details><summary>Review fault cases ({cases?.filter(entry => entry.required !== false).length ?? 0} required)</summary>
      <div className="table-scroll"><table><thead><tr><th>Sensor</th><th>Fault</th><th>Starts before failure</th><th>Role</th></tr></thead><tbody>
        {cases?.map((entry, index) => <tr key={index}><td>{entry.fault.sensor}</td><td>{entry.fault.kind}{entry.fault.kind === "drift" ? ` ${entry.fault.severity_sd} SD ${entry.fault.sign === -1 ? "down" : "up"}` : ""}<span className="note comparison-kind">{entry.fault.duration}{entry.fault.duration === "transient" ? `, ${entry.fault.length} cycles` : ""}</span></td><td>{entry.fault.onset_before_failure} cycles</td><td>{entry.required !== false ? "Required" : "Supplemental"}</td></tr>)}
      </tbody></table></div>
      <p className={styles.footnote}>Early-alarm burden counts warning time more than {String(config.transition_band_end)} cycles before failure. Faults are simulated.</p>
    </details>
    <Link to={`/experiments/${run.experiment_id}/data`} target="_blank" rel="noreferrer">Inspect data and mapping in a new tab</Link>
  </div>;
}

function AgreementSummary({ agreement }: { agreement: PilotAgreementRecord }) {
  return <details className={styles.agreement}><summary>Agreed test: {agreement.brief.equipment_family} · {modelName(agreement.candidate)}</summary>
    <dl className={styles.record}>
      <dt>Reviewer</dt><dd>{agreement.brief.reviewing_engineer}</dd>
      <dt>Current procedure</dt><dd>{agreement.brief.current_procedure}</dd>
      <dt>Intended decision</dt><dd>{agreement.brief.intended_decision}</dd>
      <dt>Success measure</dt><dd>{agreement.brief.success_measure}</dd>
      <dt>Data origin</dt><dd>{agreement.brief.data_classification} (user declared)</dd>
    </dl>
  </details>;
}

function ReviewForm({ id, reviewer, allowsTrial, onSaved }: { id: string; reviewer: string; allowsTrial: boolean; onSaved: () => void }) {
  const [value, setValue] = useState<PilotOutcomeCreate>({ reviewing_engineer: reviewer, decision: "collect_data", decision_changed: false, observations: "", baseline_review_minutes: null, sidekick_review_minutes: null, evidence_reviewed: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const edit = <K extends keyof PilotOutcomeCreate>(key: K, next: PilotOutcomeCreate[K]) => setValue(previous => ({ ...previous, [key]: next }));
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await pilots.review(id, value); onSaved(); }
    catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <Panel title="Engineer review" description="Record what the evidence changed.">
    <form className={styles.form} onSubmit={save}>
      <Input label="Reviewing engineer" required disabled={busy} maxLength={200} value={value.reviewing_engineer} onChange={e => edit("reviewing_engineer", e.target.value)} />
      <fieldset disabled={busy} className={styles.checks}><RadioGroup label="Next action" value={value.decision} onValueChange={next => edit("decision", next as PilotDecision)} options={Object.entries(decisions).filter(([key]) => allowsTrial || key !== "supervised_trial").map(([key, label]) => ({ value: key, label }))} /></fieldset>
      <Textarea label="Reason and observed findings" required disabled={busy} rows={3} maxLength={2000} value={value.observations} onChange={e => edit("observations", e.target.value)} />
      <fieldset disabled={busy} className={styles.checks}>
        <label><input type="checkbox" checked={value.decision_changed} onChange={e => edit("decision_changed", e.target.checked)} />This evidence changed my intended decision</label>
        <label><input type="checkbox" checked={value.evidence_reviewed} onChange={e => edit("evidence_reviewed", e.target.checked)} />I reviewed the final results and their limitations</label>
      </fieldset>
      <details><summary>Review time comparison (optional)</summary><div className={styles.fields}>
        <Input label="Current procedure (minutes)" type="number" min={0} max={100000} step="any" disabled={busy} value={value.baseline_review_minutes ?? ""} onChange={e => edit("baseline_review_minutes", e.target.value === "" ? null : Number(e.target.value))} />
        <Input label="With Sidekick (minutes)" type="number" min={0} max={100000} step="any" disabled={busy} value={value.sidekick_review_minutes ?? ""} onChange={e => edit("sidekick_review_minutes", e.target.value === "" ? null : Number(e.target.value))} />
      </div><p className={styles.footnote}>Provide both times or neither. Self-reported, not a proven saving.</p></details>
      {error && <p className="state error" role="alert">{error}</p>}
      <div className={styles.actions}><Button type="submit" variant="primary" loading={busy} disabled={!value.evidence_reviewed || !value.observations.trim() || !value.reviewing_engineer.trim()}>Record engineer decision</Button></div>
      <p className={styles.footnote}>Saved once against this frozen model and reserved evaluation.</p>
    </form>
  </Panel>;
}

function OutcomeSummary({ outcome, synthetic }: { outcome: PilotOutcomeRecord; synthetic: boolean }) {
  return <Panel title={decisions[outcome.decision]} aside={<Badge>Review recorded</Badge>}>
    <div className={styles.stack}>
      <dl className={styles.summary}>
        <div><dt>Reviewer</dt><dd>{outcome.reviewing_engineer}</dd></div>
        <div><dt>Decision changed</dt><dd>{outcome.decision_changed ? "Yes" : "No"}</dd></div>
        <div><dt>Reported review time difference</dt><dd>{outcome.review_minutes_saved == null ? "Not measured" : `${Math.abs(outcome.review_minutes_saved)} minutes ${outcome.review_minutes_saved < 0 ? "longer" : "saved"}`}</dd></div>
      </dl>
      <p>{outcome.observations}</p>
      <p className={styles.footnote}>Decision and timings are self-reported.{synthetic ? " This simulated pilot does not establish field performance." : " Site review is required before any supervised trial."}</p>
    </div>
  </Panel>;
}
