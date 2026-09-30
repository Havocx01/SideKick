import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { useEvidence } from "../hooks/useEvidence";
import { DecisionDetails, DecisionSummary } from "../components/DecisionSummary";
import type { CandidateVerdict, ScenarioResult } from "../api/types";
import { Badge, Callout, Panel, Select, StateBlock, Stat } from "../components/Chrome";
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
  const focus = params.get("candidate");
  const [includeSupplemental, setIncludeSupplemental] = useState(false);
  useEffect(() => setIncludeSupplemental(false), [focus]);
  function setFocus(key: string) {
    const next = new URLSearchParams(params);
    next.set("candidate", key);
    setParams(next);
  }

  const criteria = selection.data?.criteria;
  const verdicts = useMemo(() => selection.data?.ranked ?? [], [selection.data]);

  const focused = focus
    ? verdicts.find(verdict => candidateKey(verdict.candidate, verdict.config_id) === focus) ?? verdicts[0]
    : verdicts[0];

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

  return (
    <>
      <header className="page-head">
        <h1>Model comparison</h1>
        <p>
          Compare warnings before and after sensor faults.
        </p>
      </header>

      <StateBlock loading={selection.loading} error={selection.error}>
        {selection.data && criteria ? (
          <>
            <DecisionSummary selection={selection.data} />
            {invalidFocus && <p className="note" role="status">That candidate is unavailable in this experiment. Showing the leading candidate instead.</p>}

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
                      <th className="num">Clean</th>
                      <th className="num">Worst required</th>
                      <th className="num">Change (pp)</th>
                      <th className="num">Burden</th>
                      <th className="num">Lead</th>
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
                      const drop = verdict.clean.detection_fraction - verdict.worst_detection_required;
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
                          <td className="num">
                            {verdict.worst_metrics ? (
                              <span style={{ color: drop > 0.15 ? "var(--fault)" : "var(--ink-soft)" }} >
                                {drop > 0 ? "-" : drop < 0 ? "+" : ""}{number(Math.abs(drop) * 100, 1)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="num">{percent(verdict.clean.early_alarm_burden, 2)}</td>
                          <td className="num">{cycles(verdict.clean.median_lead_time)}</td>
                          <td>
                            {verdict.qualifies ? (
                              <Badge tone="ok">holds under fault</Badge>
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
                Detection: warnings 10–30 cycles before failure. Burden: time in alarm more than 45 cycles before failure. Lead: cycles. pp: percentage points.
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
                    <ScenarioHeatmap results={focusedScenarios} minDetection={criteria.min_detection_fraction} />
                  </StateBlock>
                </Panel>

                <FailureDetail verdict={focused} minDetection={criteria.min_detection_fraction} scenarios={allScenarios} />
              </div>
            ) : null}
          </>
        ) : null}
      </StateBlock>

      <DecisionDetails />
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
        <Stat label="Warned too late" value={integer(verdict.clean.late)} note="alert opened inside the final cycles" />
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
