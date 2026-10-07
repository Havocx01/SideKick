import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { useAnalysis } from "../components/AnalysisProvider";
import { DecisionDetails, DecisionSummary } from "../components/DecisionSummary";
import type { CandidateVerdict, ScenarioResult } from "../api/types";
import { Badge, Button, Callout, IconButton, Panel, Select, StateBlock, Stat } from "../components/Chrome";
import { ValidationPanel } from "../components/ValidationPanel";
import { IntervalBar } from "../components/IntervalBar";
import { ReliabilityPlot } from "../components/ReliabilityPlot";
import { ScenarioHeatmap } from "../components/ScenarioHeatmap";
import { candidateKey, candidateLabel, cycles, integer, interval, number, percent, scenarioLabel } from "../format";
import { useApi } from "../hooks/useApi";
import { Switch } from "@/registry/components/switch/switch";
import { AlertTriangle, Check, ChevronRight, GitCompare, X } from "lucide-react";
import { evidenceApi } from "../api/client";

export function ModelComparison() {
  const experimentId = useExperimentId();
  const analysis = useAnalysis();
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [params, setParams] = useSearchParams();
  const partition = params.get("partition") === "holdout" ? "holdout" : "out_of_fold";
  const api = useEvidence();
  const comparisonApi = useMemo(() => evidenceApi(experimentId, undefined, partition), [experimentId, partition]);
  const selection = useApi(() => comparisonApi.selection(), [comparisonApi]);
  const final = useApi(() => comparisonApi.finalEvaluation(), [comparisonApi]);
  const calibration = useApi(() => comparisonApi.calibration(), [comparisonApi]);
  const reproducibility = useApi(() => comparisonApi.reproducibility(), [comparisonApi]);

  const location = useLocation();
  const focus = params.get("candidate");
  const [includeSupplemental, setIncludeSupplemental] = useState(false);
  const [inspected, setInspected] = useState<ScenarioResult[]>([]);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const [faultOpen, setFaultOpen] = useState(false);
  const replayIndex = useApi(() => api.replayIndex(), [api]);
  useEffect(() => { setIncludeSupplemental(false); setInspected([]); }, [focus, partition]);
  function setFocus(key: string) {
    const next = new URLSearchParams(params);
    next.set("candidate", key);
    next.delete("equipment"); next.delete("scenario");
    setParams(next);
  }

  useEffect(() => { setSelectedModels([]); }, [experimentId, partition]);
  const criteria = selection.data?.criteria;
  const verdicts = useMemo(() => selection.data?.ranked ?? [], [selection.data]);

  const focused = focus
    ? verdicts.find(verdict => candidateKey(verdict.candidate, verdict.config_id) === focus)
    : selection.data?.recommended ?? verdicts[0];

  // Fetch only the selected candidate; the complete matrix is several megabytes.
  const focusKey = focused ? candidateKey(focused.candidate, focused.config_id) : "";
  const scenarios = useApi(
    () => (focusKey ? api.scenarios({ candidate: focusKey, includeClean: false }) : Promise.resolve([])),
    [api, focusKey]
  );
  const allScenarios = scenarios.data ?? [];
  const focusedScenarios = includeSupplemental ? allScenarios : allScenarios.filter(row => row.required);
  const invalidFocus = Boolean(focus && selection.data && !verdicts.some(v => candidateKey(v.candidate, v.config_id) === focus));
  const weakestReplay = replayIndex.data?.series.find(row => row.scenario_id === focused?.worst_scenario_id && candidateKey(row.candidate, row.config_id) === focusKey);
  const replayCases = focused ? [
    { scenarioId: focused.worst_scenario_id, label: "Replay weakest detection case" },
    { scenarioId: focused.worst_burden_scenario_id, label: "Replay highest-burden case" }
  ].filter((item, index, cases) => index === 0 || !item.scenarioId || item.scenarioId !== cases[0]?.scenarioId) : [];
  const faultQuery = new URLSearchParams({ candidate: focusKey, partition });
  if (weakestReplay) {
    faultQuery.set("equipment", weakestReplay.equipment_id);
    faultQuery.set("scenario", weakestReplay.scenario_id);
  }
  const evidenceBase = experimentId ? `/experiments/${experimentId}` : "";
  const inspectFaultHref = weakestReplay ? `${evidenceBase}/replay?${faultQuery}` : `${evidenceBase}/comparison?${faultQuery}#fault-results`;
  useEffect(() => {
    if (location.hash === "#fault-results") setFaultOpen(true);
    if (location.hash === "#fault-results" && faultOpen && selection.data) document.getElementById("fault-results")?.scrollIntoView();
  }, [location.hash, faultOpen, selection.data, scenarios.data]);

  useEffect(() => {
    if (location.hash === "#augmentation") setTechnicalOpen(true);
  }, [location.hash]);
  useEffect(() => {
    if (technicalOpen && location.hash === "#augmentation") document.getElementById("augmentation")?.scrollIntoView();
  }, [technicalOpen, location.hash]);

  return (
    <>
      <header className="page-head comparison-heading">
        <h1>Model comparison</h1>
        {selection.data && <div className="candidate-selector"><Select label="Inspect model" placeholder="Choose a model" value={focusKey} onValueChange={setFocus} options={verdicts.map(verdict => ({ value: candidateKey(verdict.candidate, verdict.config_id), label: candidateLabel(verdict.candidate, verdict.config_id) }))} /></div>}
      </header>
      {final.data?.available && <div className="partition-control" role="group" aria-label="Evaluation partition">{([["out_of_fold", "Development"], ["holdout", "Final validation"]] as const).map(([value, label]) => <Button key={value} size="sm" variant="ghost" aria-pressed={partition === value} onClick={() => { const next = new URLSearchParams(params); next.set("partition", value); next.delete("candidate"); setParams(next); }}>{label}</Button>)}</div>}

      <StateBlock loading={selection.loading} error={selection.error}>
        {selection.data && criteria ? (
          <>
            {!invalidFocus && <DecisionSummary selection={selection.data} inspected={focused} inspectFaultHref={inspectFaultHref} />}
            {invalidFocus && <p className="note" role="status">That candidate is unavailable in this experiment. Choose an available model.</p>}

            <Panel
              title="Candidate results"
              tight
              aside={analysis.enabled("compare") && <div className="analysis-selection-actions"><span>{selectedModels.length} / 2 selected</span><Button size="sm" variant="secondary" disabled={selectedModels.length !== 2} onClick={() => analysis.start({ task: "compare", experiment_id: experimentId, partition, candidates: selectedModels })}><GitCompare size={13} aria-hidden="true" />Compare selected</Button>{selectedModels.length > 0 && <IconButton label="Clear selected models" onClick={() => setSelectedModels([])}><X size={16} aria-hidden="true" /></IconButton>}</div>}
            >
              <div className="table-scroll" role="region" aria-label="Candidate results table" tabIndex={0}>
                <table className="candidate-table">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th className="num">Healthy</th>
                      <th className="num">Weakest fault</th>
                      <th className="num" title="Highest share of eligible early cycles spent in alarm across all required faults">Worst early alarm time</th>
                      <th>Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {verdicts.map(verdict => {
                      const key = candidateKey(verdict.candidate, verdict.config_id);
                      const isFocus = focused ? key === candidateKey(focused.candidate, focused.config_id) : false;
                      const isRecommended =
                        selection.data?.recommended?.candidate === verdict.candidate &&
                        selection.data?.recommended?.config_id === verdict.config_id;
                      return (
                        <tr
                          key={key}
                          className={`candidate-row${isFocus ? " row-focus" : ""}${isRecommended ? " row-recommended" : ""}`}
                          onClick={() => setFocus(key)}
                        >
                          <td>
                            <div className="candidate-cell">
                              {analysis.enabled("compare") && <label className="candidate-select" onClick={event => event.stopPropagation()}><input type="checkbox" aria-label={`Select ${candidateLabel(verdict.candidate, verdict.config_id)} for comparison`} checked={selectedModels.includes(key)} disabled={selectedModels.length === 2 && !selectedModels.includes(key)} onChange={event => setSelectedModels(current => event.target.checked ? [...current, key] : current.filter(value => value !== key))} /></label>}
                              <button type="button" className="candidate-inspect" aria-label={`Inspect ${candidateLabel(verdict.candidate, verdict.config_id)}`} aria-pressed={isFocus}>{candidateLabel(verdict.candidate, verdict.config_id)}<ChevronRight size={14} aria-hidden="true" /></button>
                              {verdict.candidate === "age_baseline" ? <Badge tone="neutral">no sensors</Badge> : null}
                            </div>
                          </td>
                          <td className="num metric-cell">
                            <span>{percent(verdict.clean.detection_fraction, 1)}</span>
                            <IntervalBar
                              value={verdict.clean.detection_fraction}
                              lower={verdict.clean.detection_ci.lower}
                              upper={verdict.clean.detection_ci.upper}
                              threshold={criteria.min_detection_fraction}
                            />
                          </td>
                          <td className="num metric-cell">
                            <span>{verdict.worst_metrics ? percent(verdict.worst_metrics.detection_fraction, 1) : "Not tested"}</span>
                            {verdict.worst_metrics ? (
                              <IntervalBar
                                value={verdict.worst_metrics.detection_fraction}
                                lower={verdict.worst_metrics.detection_ci.lower}
                                upper={verdict.worst_metrics.detection_ci.upper}
                                threshold={criteria.min_detection_fraction}
                              />
                            ) : (
                              <span className="note">not tested</span>
                            )}
                          </td>
                          <td className="num">{percent(verdict.worst_burden_required, 2)}</td>
                          <td>
                            {verdict.qualifies ? (
                              <Badge tone="ok"><span className="verdict-badge"><Check size={11} strokeWidth={2.8} aria-hidden="true" />pass</span></Badge>
                            ) : verdict.passes_clean ? (
                              <Badge tone="bad"><span className="verdict-badge"><X size={11} strokeWidth={2.8} aria-hidden="true" />fault fail</span></Badge>
                            ) : (
                              <Badge tone="warn"><span className="verdict-badge"><AlertTriangle size={11} strokeWidth={2.6} aria-hidden="true" />clean fail</span></Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <details className="leaderboard-note"><summary>Table key</summary><p className="note">Healthy and weakest fault: share of equipment histories warned {criteria.min_useful_lead} to {criteria.horizon_cycles} cycles before failure. Bars: 95% detection intervals. Worst early alarm time: maximum across all {integer(verdicts[0]?.required_scenarios ?? 0)} required faults, not necessarily the displayed weakest fault. Alarm time is a share of eligible early cycles, not a false-warning probability.</p></details>
            </Panel>

            {focused ? (
              <div id="fault-results" className="evidence-section">
                <details className="disclosure disclosure-plain" open={faultOpen} onToggle={event => setFaultOpen(event.currentTarget.open)}><summary>Sensor faults · {focused.required_passed} / {focused.required_scenarios} passed</summary>
                <Panel
                  title="Lowest detection per sensor"
                  description={includeSupplemental ? "Supplemental cases included." : undefined}
                >
                  {allScenarios.some(row => !row.required) && (
                    <div className="matrix-options"><Switch label="Include supplemental cases" checked={includeSupplemental} onCheckedChange={setIncludeSupplemental} /></div>
                  )}
                  <StateBlock loading={scenarios.loading} error={scenarios.error} empty={focusedScenarios.length === 0}>
                    <ScenarioHeatmap results={focusedScenarios} minDetection={criteria.min_detection_fraction} maxBurden={criteria.max_early_alarm_burden} expectedEngines={focused.clean.engines} onInspect={setInspected} />
                  </StateBlock>
                  {inspected.length > 0 && <section className="scenario-inspection" aria-label="Scenario details"><header className="scenario-inspection-header"><h3>Scenario details</h3><IconButton label="Close scenario details" onClick={() => setInspected([])}><X size={16} aria-hidden="true" /></IconButton></header><div className="table-scroll"><table><thead><tr><th>Case</th><th>Detection</th><th>Burden</th><th>Coverage</th><th>Outcome</th></tr></thead><tbody>{inspected.map(r => { const failures = [r.metrics.detection_fraction < criteria.min_detection_fraction ? "Detection below minimum" : "", r.metrics.early_alarm_burden == null ? "Burden unavailable" : r.metrics.early_alarm_burden > criteria.max_early_alarm_burden ? "Burden above maximum" : "", r.metrics.engines !== focused.clean.engines || r.coverage_complete === false ? "Coverage incomplete" : ""].filter(Boolean); return <tr key={r.scenario_id}><td>{r.fault ? scenarioLabel(r.scenario_id) : r.scenario_id}<span className="note comparison-kind">{r.required ? "Required" : "Supplemental"}</span></td><td>{percent(r.metrics.detection_fraction, 1)}</td><td>{percent(r.metrics.early_alarm_burden, 2)}</td><td>{r.metrics.engines}/{r.expected_engines ?? focused.clean.engines}</td><td>{failures.length ? failures.join("; ") : "Meets criteria"}</td></tr>; })}</tbody></table></div></section>}
                  <div className="actions replay-case-actions">{replayCases.map(({ scenarioId, label }) => { const entry = replayIndex.data?.series.find(s => s.scenario_id === scenarioId && `${s.candidate}/${s.config_id}` === focusKey); const query = new URLSearchParams({ candidate: focusKey, partition }); if (entry) { query.set("equipment", entry.equipment_id); query.set("scenario", entry.scenario_id); } return entry ? <Link className="button" key={label} title={focused.worst_scenario_id === focused.worst_burden_scenario_id ? "Also the highest-burden case" : undefined} to={`${experimentId ? `/experiments/${experimentId}` : ""}/replay?${query}`}>{label}</Link> : <span key={label} className="note">{label}: not stored in this bundle.</span>; })}</div>
                </Panel>
                </details>
              </div>
            ) : null}
          </>
        ) : null}
      </StateBlock>

      {experimentId && <ValidationPanel experimentId={experimentId} recommendation={selection.data?.recommended} qualifies={Boolean(selection.data?.recommended)} onCompleted={() => { final.reload(); selection.reload(); }} />}
      {final.data?.available ? (
        <Panel
          title="Held-back equipment"
          description="Separate from model selection; does not establish field performance."
        >
          {final.data.available && final.data.selection?.ranked[0] ? (
            <>
              {final.data.selection.outcome === "none_qualified" ? (
                <Callout tone="fault" title="The selected model failed the final criteria">
                  No deployment recommendation is supported by this final evaluation.
                </Callout>
              ) : null}
              <div className="grid cols-3" style={{ marginBottom: 0 }}>
                <Stat
                  label="Detection, clean"
                  value={percent(final.data.selection.ranked[0].clean.detection_fraction, 1)}
                  note={interval(
                    final.data.selection.ranked[0].clean.detection_ci.lower,
                    final.data.selection.ranked[0].clean.detection_ci.upper
                  )}
                />
                <Stat
                  label="Detection, worst fault"
                  value={percent(final.data.selection.ranked[0].worst_detection_required, 1)}
                  note={final.data.selection.ranked[0].worst_scenario_id ?? "—"}
                />
                <Stat
                  label="Median lead"
                  value={cycles(final.data.selection.ranked[0].clean.median_lead_time)}
                  note="cycles of warning before failure"
                />
              </div>
            </>
          ) : (
            <p className="note">{final.data.note ?? "Not yet scored."}</p>
          )}
        </Panel>
      ) : null}

      <details className="technical-details disclosure-plain" open={technicalOpen} onToggle={event => setTechnicalOpen(event.currentTarget.open)}>
        <summary>Technical details</summary>
        <div role="group" aria-label="Technical details">
      {focused && criteria && <FailureDetail verdict={focused} minDetection={criteria.min_detection_fraction} scenarios={allScenarios} />}
      {final.data && !final.data.available && <p className="note">Reserved evaluation: {final.data.note ?? "Not yet scored."}</p>}
      <DecisionDetails />
      <StateBlock loading={calibration.loading} error={calibration.error}>
        {calibration.data && calibration.data.length > 0 ? (
          <Panel
            title="Are the scores probabilities?"
            description="Below the diagonal, scores overstate risk. Poor calibration means scores should rank risk, not estimate probability."
          >
            <ReliabilityPlot reports={calibration.data} />
          </Panel>
        ) : null}
      </StateBlock>

      {reproducibility.data?.available && reproducibility.data.check ? (
        <Panel
          title="Reproducibility"
          description="Two runs with the same seed."
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {reproducibility.data.check.reproduced ? (
              <Badge tone="ok">reproduced</Badge>
            ) : (
              <Badge tone="bad">differs by {number(reproducibility.data.check.max_absolute_difference, 6)}</Badge>
            )}
            <span className="note">
              {integer(reproducibility.data.check.metrics_compared)} metrics compared between{" "}
              <span className="mono">{reproducibility.data.check.run_id}</span> and{" "}
              <span className="mono">{reproducibility.data.check.repeat_run_id}</span>, to a tolerance of{" "}
              {number(reproducibility.data.check.tolerance, 9)}
            </span>
          </div>
        </Panel>
      ) : null}
        </div>
      </details>
    </>
  );
}

function FailureDetail({ verdict, minDetection, scenarios }: { verdict: CandidateVerdict; minDetection: number; scenarios: ScenarioResult[] }) {
  const failing = verdict.failing_scenarios ?? [];
  const worst = scenarios.find(row => row.required && row.scenario_id === verdict.worst_scenario_id)?.metrics;

  return (
    <Panel
      title="Outcome breakdown"
      description="Original readings, evaluated on equipment excluded from training."
    >
      <div className="grid cols-4" style={{ marginBottom: failing.length > 0 ? 14 : 0 }}>
        <Stat
          label="Warned in time"
          value={`${integer(verdict.clean.detected)} / ${integer(verdict.clean.engines)}`}
          note={`${percent(verdict.clean.detection_fraction, 1)} of histories`}
        />
        <Stat label="Warned too late" value={integer(verdict.clean.late)} note="alert active after the useful window" />
        <Stat
          label="Missed"
          value={integer(verdict.clean.missed)}
          note="no useful or late warning"
        />
        <Stat
          label="New alerts"
          value={number(verdict.clean.new_episodes_per_1000, 1)}
          note={`per 1,000 early-life cycles · threshold ${number(verdict.threshold, 3)}`}
        />
      </div>

      {worst && (
        <p className="fault-outcome"><strong>Weakest required case:</strong> {scenarioLabel(verdict.worst_scenario_id ?? "")}. {integer(worst.detected)} warned in time, {integer(worst.late)} late, {integer(worst.missed)} missed out of {integer(worst.engines)} histories.</p>
      )}
      {failing.length > 0 ? (
        <>
          <p className="note" style={{ marginBottom: 6 }}>
            Required scenarios failing the {percent(minDetection)} detection minimum or the alarm-burden limit:
          </p>
          <div className="pill-row">
            {failing.map((scenario: string) => (
              <span className="tool-chip failed" key={scenario}>
                {scenarioLabel(scenario)}
              </span>
            ))}
          </div>
        </>
      ) : null}
    </Panel>
  );
}
