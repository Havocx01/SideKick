import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";
import type { AcceptanceCriteria, CandidateVerdict } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { walkthroughPath, walkthroughStep, walkthroughSteps } from "../walkthrough";
import { Badge, Panel, StateBlock } from "../components/Chrome";
import { EvidenceExport } from "../components/DecisionSummary";
import { WarningCounts, WarningDefinitions } from "../components/ResultStory";
import { ReplayExample } from "../components/ReplayExample";
import { WalkthroughProgress } from "../components/cult/WalkthroughProgress";
import { GuidedModelRows, WalkthroughChoice, WarningWindow } from "../components/WalkthroughTools";
import { WalkthroughSpotlight } from "../components/WalkthroughSpotlight";
import { candidateLabel, integer, percent, scenarioLabel, scenarioSummary } from "../format";

export function Walkthrough() {
  const [params] = useSearchParams();
  const step = walkthroughStep(params);
  const index = walkthroughSteps.indexOf(step);
  const reduced = useReducedMotion();
  const api = useEvidence();
  const selection = useApi(() => api.selection(), [api]);
  const traces = useApi(() => step.id === "replay" ? api.replay("16") : Promise.resolve([]), [api, step.id]);
  const report = useApi(() => step.id === "report" ? api.decision() : Promise.resolve(null), [api, step.id]);
  const model = selection.data?.ranked.find(v => v.candidate === "logistic_regression" && v.config_id === "lr2");
  const ordinary = selection.data?.ranked.find(v => v.candidate === "xgboost" && v.config_id === "xgb1");
  const augmented = selection.data?.ranked.find(v => v.candidate === "xgboost_augmented" && v.config_id === "aug3");
  const fault = traces.data?.find(s => s.candidate === "logistic_regression" && s.config_id === "lr2" && s.scenario_id === model?.worst_scenario_id);
  const clean = traces.data?.find(s => s.candidate === "logistic_regression" && s.config_id === "lr2" && s.scenario_id === "clean");
  const criteria = selection.data?.criteria;
  const missing = !criteria || (["clean", "fault", "replay"].includes(step.id) && !model);
  const previous = walkthroughSteps[index - 1];
  const next = walkthroughSteps[index + 1];
  const guideReady = !selection.loading && !selection.error && !missing && (
    step.id === "replay" ? !!fault && !!clean && !traces.loading :
    step.id === "compare" ? !!ordinary || !!augmented : step.id === "report" ? !!augmented && !report.loading : true);
  return <div className="guided-walkthrough">
    <header className="page-head walkthrough-heading"><h1>{step.title}</h1><p>{step.instruction}</p><p className="walkthrough-mobile-source">Recorded NASA benchmark · Development</p></header>
    <div className="walkthrough-bar">
      <div className="walkthrough-step-group">
        <nav className="walkthrough-steps" aria-label="Walkthrough steps">
          {walkthroughSteps.map((item, i) => <Link key={item.id} to={walkthroughPath(item.id)} aria-current={item.id === step.id ? "step" : undefined}><span>{i + 1}</span>{item.label}</Link>)}
        </nav>
        <WalkthroughProgress currentStep={index + 1} totalSteps={walkthroughSteps.length} />
      </div>
      <div className="walkthrough-navigation">{previous ? <Link className="button" to={walkthroughPath(previous.id)}>Back</Link> : <Link className="button" to="/">Back to overview</Link>}<span>Step {index + 1} of {walkthroughSteps.length}</span>{next ? <Link className="button primary" to={walkthroughPath(next.id)}>Next</Link> : <Link className="button" aria-label="Restart walkthrough" to={walkthroughPath("clean")}>Restart</Link>}</div>
    </div>
    <StateBlock loading={selection.loading} error={selection.error}>
      {missing ? <Panel title="This walkthrough evidence is unavailable"><p>The recorded benchmark must include the named models and their fault results. No substitute results are shown.</p><Link to="/comparison">Explore available benchmark evidence</Link></Panel> : criteria && <motion.div key={step.id} data-testid="walkthrough-result"
        initial={reduced ? false : { opacity: .8 }} animate={{ opacity: 1 }} transition={{ duration: reduced ? 0 : motionTokens.duration.fast }}>
        {step.id === "clean" && model && <Panel title={candidateLabel(model.candidate, model.config_id)}>
          <div className="guided-healthy-layout"><WarningCounts metrics={model.clean} label="Healthy sensors" /><WarningWindow criteria={criteria} /></div>
          <p className="note walkthrough-boundary">Recorded development results. Test limits are demonstration settings.</p>
        </Panel>}
        {step.id === "fault" && model && <FaultStep model={model} criteria={criteria} />}
        {step.id === "replay" && <StateBlock loading={traces.loading} error={traces.error}>{fault && clean ? <>
          <ReplayExample series={fault} comparison={clean} horizon={criteria.horizon_cycles} minLead={criteria.min_useful_lead} guided />
          <details className="disclosure-plain"><summary>Replay source</summary><p className="note">{candidateLabel(fault.candidate, fault.config_id)} · Equipment {fault.equipment_id}. Verified reconstruction checked against the original benchmark. One example, not fleet-wide performance.</p></details>
        </> : <p className="state">The verified clean/faulted pair for equipment 16 is not stored. Open the full comparison to inspect fleet-wide results.</p>}</StateBlock>}
        {step.id === "compare" && <CompareStep models={[ordinary, augmented].filter((v): v is CandidateVerdict => !!v)} />}
        {step.id === "report" && <Panel title="Decision report">
          {augmented ? <>
            <dl className="walkthrough-report-preview" data-testid="walkthrough-report-preview">
              <div><dt>Decision</dt><dd><strong>{augmented.qualifies === true ? "Fresh validation required" : augmented.qualifies === false ? "Revise before further evaluation" : "Qualification unavailable"}</strong><span>{candidateLabel(augmented.candidate, augmented.config_id)} · Development</span></dd></div>
              <div><dt>Weakest scenario</dt><dd>{augmented.worst_scenario_id ? scenarioSummary(augmented.worst_scenario_id) : "Unavailable"}{augmented.worst_metrics && <span>{integer(augmented.worst_metrics.detected)} / {integer(augmented.worst_metrics.engines)} histories warned in time</span>}</dd></div>
              <div><dt>Next checks</dt><dd><StateBlock loading={report.loading} error={report.error}>{report.data?.inspected_candidate === step.candidate && report.data.partition === "out_of_fold"
                ? report.data.guide.find(answer => answer.question === "What should I inspect next?")?.answer ?? "No next check is recorded. Review the report limitations."
                : !report.loading && !report.error ? "No scoped decision is available. Review the report limitations." : null}</StateBlock></dd></div>
            </dl>
            <div className="walkthrough-report-actions"><EvidenceExport labels /></div>
          </> : <p className="state">The report candidate is unavailable in this benchmark.</p>}
          <details className="disclosure-plain"><summary>What's included?</summary><p>HTML decision report, CSV metrics and JSON evidence. The report covers aug3 development results; the ZIP includes all experiment metrics. Raw uploads and model files are excluded.</p></details>
          <p className="note walkthrough-boundary">Evidence for review, not deployment approval.</p>
        </Panel>}
      </motion.div>}
    </StateBlock>
    <div className="walkthrough-footer">
      {/* {step.id !== "report" && <Link className="walkthrough-exit" to={`/comparison?${new URLSearchParams({ candidate: step.candidate, partition: "out_of_fold" })}`}>Full results</Link>} */}
      <WalkthroughSpotlight step={step.id} ready={guideReady} criteria={criteria} />
    </div>
  </div>;
}

function FaultStep({ model, criteria }: { model: CandidateVerdict; criteria: AcceptanceCriteria }) {
  const [readings, setReadings] = useState<"healthy" | "fault">("fault");
  const metrics = readings === "fault" && model.worst_metrics ? model.worst_metrics : model.clean;
  const faultLabel = model.worst_scenario_id?.startsWith("dropout-") ? "Missing readings" : "Faulted readings";
  const difference = model.worst_metrics && model.worst_metrics.engines === model.clean.engines ? model.clean.detected - model.worst_metrics.detected : null;
  const isFault = readings === "fault" && !!model.worst_metrics;
  return <Panel title={candidateLabel(model.candidate, model.config_id)}>
    <div className="guided-step-toolbar"><WalkthroughChoice label="Sensor readings" value={isFault ? "fault" : "healthy"}
      options={[{ value: "healthy", label: "Healthy" }, { value: "fault", label: faultLabel, disabled: !model.worst_metrics }]} onChange={setReadings} />
      <Badge tone={metrics.detection_fraction < criteria.min_detection_fraction ? "bad" : "ok"}>{metrics.detection_fraction < criteria.min_detection_fraction ? "Below" : "Meets"} {percent(criteria.min_detection_fraction)} detection minimum</Badge></div>
    <p className="note guided-fault-source">{model.worst_scenario_id ? scenarioLabel(model.worst_scenario_id) : "Fault scenario unavailable"}</p>
    <div data-testid="guided-warning-result" className="guided-warning-result" aria-live="polite"><WarningCounts metrics={metrics} label={isFault ? faultLabel : "Healthy sensors"} fault={isFault} animated /></div>
    <p className="result-consequence">{difference === null ? "Counts cannot be compared with equal coverage." : difference > 0 ? <><strong>{integer(difference)}</strong> fewer timely {difference === 1 ? "warning" : "warnings"} with the fault</> : difference < 0 ? <><strong>{integer(-difference)}</strong> more timely warnings with the fault</> : "No change in timely warnings with the fault"}</p>
    {!model.worst_metrics && <p className="note">Fault measurements are unavailable. Healthy readings are still shown.</p>}
    <WarningDefinitions verdict={model} criteria={criteria} />
  </Panel>;
}

function CompareStep({ models }: { models: CandidateVerdict[] }) {
  const [emphasis, setEmphasis] = useState<"warnings" | "tests">("warnings");
  return <Panel title="Which warnings survive the required faults?">
    {models.length ? <>
      <div className="guided-step-toolbar"><WalkthroughChoice label="Comparison focus" value={emphasis} onChange={setEmphasis}
        options={[{ value: "warnings", label: "Timely warnings" }, { value: "tests", label: "Fault tests" }]} /><span className="note">Same required tests</span></div>
      <GuidedModelRows models={models} emphasis={emphasis} />
      {models.length < 2 && <p className="note">One comparison candidate is unavailable. No substitute model is shown.</p>}
      <p className="note walkthrough-boundary">This comparison does not prove augmented training helped.</p>
      <details className="disclosure-plain"><summary>Detailed comparison</summary>
        <div className="table-scroll"><table className="walkthrough-comparison" aria-label="Recorded model comparison"><thead><tr><th>Model</th><th>Healthy sensors</th><th>Weakest required fault</th><th>Required cases passed</th></tr></thead><tbody>{models.map(v => <tr key={v.config_id}><td>{candidateLabel(v.candidate, v.config_id)}</td><td>{integer(v.clean.detected)} / {integer(v.clean.engines)}</td><td>{v.worst_metrics ? `${integer(v.worst_metrics.detected)} / ${integer(v.worst_metrics.engines)}` : "Unavailable"}</td><td>{v.required_passed} / {v.required_scenarios}</td></tr>)}</tbody></table></div>
        <p className="note">The weakest faults can differ. These historical configurations do not isolate augmentation's effect. ABB field performance is unverified.</p>
      </details>
    </> : <p className="state">The named comparison candidates are unavailable in this benchmark.</p>}
  </Panel>;
}
