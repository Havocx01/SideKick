import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { DecisionDetails, DecisionSummary } from "../components/DecisionSummary";
import type { CandidateVerdict, ScenarioResult } from "../api/types";
import { Badge, Button, Callout, Panel, Select, StateBlock, Stat } from "../components/Chrome";
import { ValidationPanel } from "../components/ValidationPanel";
import { IntervalBar } from "../components/IntervalBar";
import { ReliabilityPlot } from "../components/ReliabilityPlot";
import { ScenarioHeatmap } from "../components/ScenarioHeatmap";
import { candidateKey, candidateLabel, cycles, integer, interval, number, percent, scenarioLabel } from "../format";
import { useApi } from "../hooks/useApi";
import { Switch } from "@/registry/components/switch/switch";

export function ModelComparison() {
  const api = useEvidence();
  const selection = useApi(() => api.selection(), [api]);
  const final = useApi(() => api.finalEvaluation(), [api]);
  const calibration = useApi(() => api.calibration(), [api]);
  const reproducibility = useApi(() => api.reproducibility(), [api]);

  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const experimentId = useExperimentId();
  const partition = params.get("partition") === "holdout" ? "holdout" : "out_of_fold";
  const focus = params.get("candidate");
  const [includeSupplemental, setIncludeSupplemental] = useState(false);
  const [inspected, setInspected] = useState<ScenarioResult[]>([]);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const replayIndex = useApi(() => api.replayIndex(), [api]);
  useEffect(() => { setIncludeSupplemental(false); setInspected([]); }, [focus, partition]);
  function setFocus(key: string) {
    const next = new URLSearchParams(params);
    next.set("candidate", key);
    next.delete("equipment"); next.delete("scenario");
    setParams(next);
  }

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
  useEffect(() => {
    if (location.hash === "#fault-results" && selection.data) document.getElementById("fault-results")?.scrollIntoView();
  }, [location.hash, selection.data, scenarios.data]);

  useEffect(() => {
    if (location.hash === "#augmentation") setTechnicalOpen(true);
  }, [location.hash]);
  useEffect(() => {
    if (technicalOpen && location.hash === "#augmentation") document.getElementById("augmentation")?.scrollIntoView();
  }, [technicalOpen, location.hash]);

  return (
    <>
      <header className="page-head">
        <h1>Model comparison</h1>
        <p>
          Compare warnings before and after sensor faults.
        </p>
      </header>
      {final.data?.available && <div className="partition-control" role="group" aria-label="Evaluation partition">{([["out_of_fold", "Development"], ["holdout", "Final validation"]] as const).map(([value, label]) => <Button key={value} variant={partition === value ? "primary" : "secondary"} aria-pressed={partition === value} onClick={() => { const next = new URLSearchParams(params); next.set("partition", value); next.delete("candidate"); setParams(next); }}>{label}</Button>)}</div>}

      <StateBlock loading={selection.loading} error={selection.error}>
        {selection.data && criteria ? (
          <>
            {!invalidFocus && <DecisionSummary selection={selection.data} inspected={focused} />}
            {invalidFocus && <p className="note" role="status">That candidate is unavailable in this experiment. Select an available model below to inspect it.</p>}

            <Panel
              title="Candidate results"
              description={
                <>
                  {integer(verdicts[0]?.required_scenarios ?? 0)} required fault cases · Bars show 95% detection intervals.
                </>
              }
              tight
            >
              <div className="table-scroll">
                <table className="candidate-table">
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th className="num">Healthy sensors</th>
                      <th className="num">Weakest fault</th>
                      <th className="num">Early alarm time</th>
                      <th className="num">Highest fault alarm time</th>
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
                          onClick={() => setFocus(key)}
                          tabIndex={0}
                          aria-label={`Inspect ${candidateLabel(verdict.candidate, verdict.config_id)}`}
                          onKeyDown={event => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              setFocus(key);
                            }
                          }}
                          className={isFocus ? "row-focus" : undefined}
                          style={{ cursor: "pointer" }}
                        >
                          <td>
                            <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 4 }}>
                              <span>{candidateLabel(verdict.candidate, verdict.config_id)}</span>
                              {isRecommended ? <Badge tone="ok">recommended</Badge> : null}
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
                          <td className="num">{percent(verdict.clean.early_alarm_burden, 2)}</td>
                          <td className="num">{percent(verdict.worst_burden_required, 2)}</td>
                          <td>
                            {verdict.qualifies ? (
                              <Badge tone="ok">meets {partition === "holdout" ? "final" : "development"} criteria</Badge>
                            ) : verdict.passes_clean ? (
                              <Badge tone="bad">fails under fault</Badge>
                            ) : (
                              <Badge tone="warn">fails on clean data</Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="note leaderboard-note">
                Detection: alert active {criteria.min_useful_lead} to {criteria.horizon_cycles} cycles before failure. Burden: eligible time in alarm.
              </p>
            </Panel>

            {focused ? (
              <div id="fault-results" className="evidence-section">
                <Panel
                  title={`Sensor fault results: ${candidateLabel(focused.candidate, focused.config_id)}`}
                  description={includeSupplemental ? "Lowest detection per sensor and fault. Supplemental cases included." : "Lowest detection per sensor and fault, across required cases."}
                  aside={
                    <div className="candidate-selector"><Select label="Inspect candidate" value={candidateKey(focused.candidate, focused.config_id)} onValueChange={setFocus} options={verdicts.map(verdict => ({ value: candidateKey(verdict.candidate, verdict.config_id), label: candidateLabel(verdict.candidate, verdict.config_id) }))} /></div>
                  }
                >
                  {allScenarios.some(row => !row.required) && (
                    <div className="matrix-options"><Switch label="Include supplemental cases" checked={includeSupplemental} onCheckedChange={setIncludeSupplemental} /></div>
                  )}
                  <StateBlock loading={scenarios.loading} error={scenarios.error} empty={focusedScenarios.length === 0}>
                    <ScenarioHeatmap results={focusedScenarios} minDetection={criteria.min_detection_fraction} maxBurden={criteria.max_early_alarm_burden} expectedEngines={focused.clean.engines} onInspect={setInspected} />
                  </StateBlock>
                  {inspected.length > 0 && <section className="scenario-inspection" aria-label="Scenario details"><h3>Scenario details</h3><div className="table-scroll"><table><thead><tr><th>Case</th><th>Detection</th><th>Burden</th><th>Coverage</th><th>Outcome</th></tr></thead><tbody>{inspected.map(r => { const failures = [r.metrics.detection_fraction < criteria.min_detection_fraction ? "Detection below minimum" : "", r.metrics.early_alarm_burden == null ? "Burden unavailable" : r.metrics.early_alarm_burden > criteria.max_early_alarm_burden ? "Burden above maximum" : "", r.metrics.engines !== focused.clean.engines || r.coverage_complete === false ? "Coverage incomplete" : ""].filter(Boolean); return <tr key={r.scenario_id}><td>{r.fault ? scenarioLabel(r.scenario_id) : r.scenario_id}<span className="note comparison-kind">{r.required ? "Required" : "Supplemental"}</span></td><td>{percent(r.metrics.detection_fraction, 1)}</td><td>{percent(r.metrics.early_alarm_burden, 2)}</td><td>{r.metrics.engines}/{r.expected_engines ?? focused.clean.engines}</td><td>{failures.length ? failures.join("; ") : "Meets criteria"}</td></tr>; })}</tbody></table></div><Button variant="ghost" onClick={() => setInspected([])}>Close scenario details</Button></section>}
                  <div className="actions replay-case-actions">{[[focused.worst_scenario_id, "Replay weakest detection case"], [focused.worst_burden_scenario_id, "Replay highest-burden case"]].map(([scenarioId, label]) => { const entry = replayIndex.data?.series.find(s => s.scenario_id === scenarioId && `${s.candidate}/${s.config_id}` === focusKey); const query = new URLSearchParams({ candidate: focusKey, partition }); if (entry) { query.set("equipment", entry.equipment_id); query.set("scenario", entry.scenario_id); } return entry ? <Link className="button" key={label} to={`${experimentId ? `/experiments/${experimentId}` : ""}/replay?${query}`}>{label}</Link> : <span key={label} className="note">{label}: not stored in this bundle.</span>; })}</div>
                </Panel>

                <FailureDetail verdict={focused} minDetection={criteria.min_detection_fraction} scenarios={allScenarios} />
              </div>
            ) : null}
          </>
        ) : null}
      </StateBlock>

      {experimentId && <ValidationPanel experimentId={experimentId} recommendation={selection.data?.recommended} qualifies={Boolean(selection.data?.recommended)} onCompleted={() => { final.reload(); selection.reload(); }} />}
      {final.data ? (
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

      <details className="technical-details" open={technicalOpen} onToggle={event => setTechnicalOpen(event.currentTarget.open)}>
        <summary>Technical details</summary>
        <div role="group" aria-label="Technical details">
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
