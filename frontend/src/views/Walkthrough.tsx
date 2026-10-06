import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { walkthroughPath, walkthroughStep, walkthroughSteps } from "../walkthrough";
import { Badge, Panel, StateBlock } from "../components/Chrome";
import { EvidenceExport } from "../components/DecisionSummary";
import { ResultStory, WarningCounts } from "../components/ResultStory";
import { ReplayExample } from "../components/ReplayExample";
import { candidateLabel, integer, percent } from "../format";

export function Walkthrough() {
  const [params] = useSearchParams();
  const step = walkthroughStep(params);
  const index = walkthroughSteps.indexOf(step);
  const api = useEvidence();
  const selection = useApi(() => api.selection(), [api]);
  const traces = useApi(() => step.id === "replay" ? api.replay("16") : Promise.resolve([]), [api, step.id]);
  const model = selection.data?.ranked.find(v => v.candidate === "logistic_regression" && v.config_id === "lr2");
  const ordinary = selection.data?.ranked.find(v => v.candidate === "xgboost" && v.config_id === "xgb1");
  const augmented = selection.data?.ranked.find(v => v.candidate === "xgboost_augmented" && v.config_id === "aug3");
  const fault = traces.data?.find(s => s.candidate === "logistic_regression" && s.config_id === "lr2" && s.scenario_id === model?.worst_scenario_id);
  const clean = traces.data?.find(s => s.candidate === "logistic_regression" && s.config_id === "lr2" && s.scenario_id === "clean");
  const criteria = selection.data?.criteria;
  const missing = !model || !criteria || (step.id === "fault" && !model.worst_metrics) || (step.id === "compare" && (!ordinary?.worst_metrics || !augmented?.worst_metrics));
  const descriptions = {
    clean: "Unchanged readings. Warnings before equipment failure.",
    fault: "Sensor 8 stops reporting. Same model, same warning rule.",
    replay: "Equipment 16. One stored example.",
    compare: "Same tests. Different models.",
    report: "Results and settings, ready to review."
  };
  const previous = walkthroughSteps[index - 1];
  const next = walkthroughSteps[index + 1];
  return <>
    <header className="page-head walkthrough-heading"><h1>{step.title}</h1><p>{descriptions[step.id]}</p></header>
    <div className="walkthrough-bar">
      <nav className="walkthrough-steps" aria-label="Walkthrough steps">
        {walkthroughSteps.map((item, i) => <Link key={item.id} to={walkthroughPath(item.id)} aria-current={item.id === step.id ? "step" : undefined}><span>{i + 1}</span>{["Healthy", "Fault", "Replay", "Compare", "Report"][i]}</Link>)}
      </nav>
      <div className="walkthrough-navigation">{previous ? <Link className="button" to={walkthroughPath(previous.id)}>Back</Link> : <Link className="button" to="/">Back to overview</Link>}<span>Step {index + 1} of {walkthroughSteps.length}</span>{next ? <Link className="button primary" to={walkthroughPath(next.id)}>Next</Link> : <Link className="button" to={walkthroughPath("clean")}>Restart walkthrough</Link>}</div>
    </div>
    <StateBlock loading={selection.loading} error={selection.error}>
      {missing ? <Panel title="This walkthrough evidence is unavailable"><p>The recorded benchmark must include the named models and their fault results. No substitute results are shown.</p><Link to="/comparison">Explore available benchmark evidence</Link></Panel> : <div data-testid="walkthrough-result">
        {step.id === "clean" && <Panel title="Logistic regression · lr2"><WarningCounts metrics={model.clean} label="Healthy sensors" /><p className="note useful-window">In time = {criteria.min_useful_lead}–{criteria.horizon_cycles} cycles before failure.</p></Panel>}
        {step.id === "fault" && <Panel title="Logistic regression · lr2" aside={<Badge tone={model.worst_metrics!.detection_fraction < criteria.min_detection_fraction ? "bad" : "ok"}>{model.worst_metrics!.detection_fraction < criteria.min_detection_fraction ? "Below" : "Meets"} {percent(criteria.min_detection_fraction)} minimum</Badge>}><ResultStory verdict={model} criteria={criteria} /></Panel>}
        {step.id === "replay" && <StateBlock loading={traces.loading} error={traces.error}>{fault && clean ? <><ReplayExample series={fault} comparison={clean} horizon={criteria.horizon_cycles} minLead={criteria.min_useful_lead} /><details><summary>Replay source</summary><p className="note">Logistic regression · lr2 · Equipment 16. Verified reconstruction checked against the original benchmark. One example, not fleet-wide performance.</p></details></> : <p className="state">The verified clean/faulted pair for equipment 16 is not stored. Open the full comparison to inspect fleet-wide results.</p>}</StateBlock>}
        {step.id === "compare" && ordinary && augmented && <Panel title="Which warnings survive the required faults?">
          <div className="table-scroll"><table className="walkthrough-comparison"><thead><tr><th>Model</th><th>Healthy sensors</th><th>Weakest required fault</th><th>Required cases passed</th></tr></thead><tbody>{[ordinary, augmented].map(v => <tr key={v.config_id}><td>{candidateLabel(v.candidate, v.config_id)}</td><td>{integer(v.clean.detected)} / {integer(v.clean.engines)}</td><td>{integer(v.worst_metrics?.detected)} / {integer(v.worst_metrics?.engines)}</td><td>{v.required_passed} / {v.required_scenarios}</td></tr>)}</tbody></table></div>
          <p className="result-consequence">{ordinary.worst_metrics?.detected === augmented.worst_metrics?.detected && ordinary.worst_metrics?.engines === augmented.worst_metrics?.engines ? "Same weakest-case detection." : "Different weakest-case detection."}</p>
          <p className="note">This comparison does not prove augmented training helped.</p>
          <details><summary>Comparison limits</summary><p>The weakest faults can differ. These historical configurations do not isolate augmentation's effect. Test limits are demonstration settings; ABB field performance is unverified.</p></details>
        </Panel>}
        {step.id === "report" && <Panel title="Decision report" aside={<EvidenceExport />}><div className="report-contents"><span>HTML report</span><span>CSV metrics</span><span>JSON evidence</span></div><p className="note">Report: aug3 · Development. ZIP: all experiment metrics.</p><details><summary>What's included?</summary><p>Results, settings, source identifiers and limitations. Raw uploads and model files are excluded. This is evidence for review, not deployment approval.</p></details><div className="actions"><Link className="button" to="/comparison?candidate=xgboost_augmented%2Faug3">Open full comparison</Link><Link className="button" to="/">New experiment</Link></div></Panel>}
      </div>}
    </StateBlock>
    {step.id !== "report" && <Link className="walkthrough-exit" to={`/comparison?${new URLSearchParams({ candidate: step.candidate, partition: "out_of_fold" })}`}>Full results</Link>}
  </>;
}
