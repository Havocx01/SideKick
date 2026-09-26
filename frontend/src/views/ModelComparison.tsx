import { useMemo, useState } from "react";

import { useEvidence } from "../hooks/useEvidence";
import { DecisionSummary } from "../components/DecisionSummary";
import type { CandidateVerdict } from "../api/types";
import { Badge, Callout, Panel, StateBlock, Stat } from "../components/Chrome";
import { IntervalBar } from "../components/IntervalBar";
import { ReliabilityPlot } from "../components/ReliabilityPlot";
import { ScenarioHeatmap } from "../components/ScenarioHeatmap";
import { candidateKey, candidateLabel, cycles, integer, interval, number, percent } from "../format";
import { useApi } from "../hooks/useApi";

export function ModelComparison() {
  const api = useEvidence();
  const selection = useApi(() => api.selection(), [api]);
  const final = useApi(() => api.finalEvaluation(), [api]);
  const calibration = useApi(() => api.calibration(), [api]);
  const reproducibility = useApi(() => api.reproducibility(), [api]);

  const [focus, setFocus] = useState<string | null>(null);

  const criteria = selection.data?.criteria;
  const verdicts = useMemo(() => selection.data?.ranked ?? [], [selection.data]);

  const focused = focus
    ? verdicts.find(verdict => candidateKey(verdict.candidate, verdict.config_id) === focus)
    : verdicts[0];

  // Fetch only the selected candidate; the complete matrix is several megabytes.
  const focusKey = focused ? candidateKey(focused.candidate, focused.config_id) : "";
  const scenarios = useApi(
    () => (focusKey ? api.scenarios({ candidate: focusKey, includeClean: false }) : Promise.resolve([])),
    [api, focusKey]
  );
  const focusedScenarios = scenarios.data ?? [];

  return (
    <>
      <header className="page-head">
        <h1>Model comparison</h1>
        <p>
          Candidates must pass the detection and alarm-burden limits on clean data and every required fault case.
          Qualifying models are ranked by mean detection across those cases, with clean alarm burden breaking ties.
          These simulated tests do not establish field performance.
        </p>
      </header>

      <DecisionSummary />
      <div id="fault-results" />
      <StateBlock loading={selection.loading} error={selection.error}>
        {selection.data && criteria ? (
          <>
            <Recommendation
              outcome={selection.data.outcome}
              recommended={selection.data.recommended ?? null}
              notes={selection.data.notes ?? []}
              uncertain={selection.data.uncertain_comparisons ?? []}
              minDetection={criteria.min_detection_fraction}
              maxBurden={criteria.max_early_alarm_burden}
            />

            <Panel
              title="Leaderboard"
              description={
                <>
                  Worst case is the weakest result across the {integer(verdicts[0]?.required_scenarios ?? 0)} required
                  fault scenarios. Bars show per-case 95% detection intervals on development engines. They are not a
                  statistical test of the ranking. Select a candidate to inspect its faults.
                </>
              }
              tight
            >
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Candidate</th>
                      <th style={{ width: 150 }}>Detection, clean</th>
                      <th className="num">Clean</th>
                      <th style={{ width: 150 }}>Detection, worst fault</th>
                      <th className="num">Worst</th>
                      <th className="num">Drop</th>
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
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span>{candidateLabel(verdict.candidate, verdict.config_id)}</span>
                              {isRecommended ? <Badge tone="ok">recommended</Badge> : null}
                              {verdict.candidate === "age_baseline" ? <Badge tone="neutral">no sensors</Badge> : null}
                            </div>
                          </td>
                          <td>
                            <IntervalBar
                              value={verdict.clean.detection_fraction}
                              lower={verdict.clean.detection_ci.lower}
                              upper={verdict.clean.detection_ci.upper}
                              threshold={criteria.min_detection_fraction}
                            />
                          </td>
                          <td className="num">{percent(verdict.clean.detection_fraction, 1)}</td>
                          <td>
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
                            {verdict.worst_metrics ? percent(verdict.worst_metrics.detection_fraction, 1) : "—"}
                          </td>
                          <td className="num">
                            {verdict.worst_metrics ? (
                              <span style={{ color: drop > 0.15 ? "var(--fault)" : "var(--ink-soft)" }} >
                                {drop > 0 ? "−" : ""}
                                {percent(Math.abs(drop), 1)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="num">{percent(verdict.clean.early_alarm_burden, 1)}</td>
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
              <p className="note" style={{ marginTop: 10 }}>
                Burden is the share of eligible early-life cycles spent in alarm, excluding the transition band. Lead is
                the median lead time for useful detections. Select a row to see its fault detail below.
              </p>
            </Panel>

            {focused ? (
              <>
                <Panel
                  title={`Where ${candidateLabel(focused.candidate, focused.config_id)} breaks`}
                  description="Every fault scenario tested, as the sensor that failed against how it failed. One dark row means a single channel this candidate depends on; a dark column means a failure mode it cannot tolerate on any channel."
                  aside={
                    <div className="pill-row">
                      {verdicts.map(verdict => {
                        const key = candidateKey(verdict.candidate, verdict.config_id);
                        const active = key === candidateKey(focused.candidate, focused.config_id);
                        return (
                          <button key={key} onClick={() => setFocus(key)} className={active ? "active" : undefined}>
                            {candidateLabel(verdict.candidate, verdict.config_id)}
                          </button>
                        );
                      })}
                    </div>
                  }
                >
                  <StateBlock loading={scenarios.loading} error={scenarios.error} empty={focusedScenarios.length === 0}>
                    <ScenarioHeatmap results={focusedScenarios} minDetection={criteria.min_detection_fraction} />
                  </StateBlock>
                </Panel>

                <FailureDetail verdict={focused} minDetection={criteria.min_detection_fraction} />
              </>
            ) : null}
          </>
        ) : null}
      </StateBlock>

      {final.data ? (
        <Panel
          title="Held-back equipment"
          description="Final evaluation is separate from model selection. Even an untouched holdout from this simulated dataset cannot establish performance on plant equipment."
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
            description="Observed failure rate against predicted score. Points below the diagonal mean the score overstates the risk. Where a curve departs from the line, treat the score as a ranking and not as a likelihood."
          >
            <ReliabilityPlot reports={calibration.data} />
          </Panel>
        ) : null}
      </StateBlock>

      {reproducibility.data?.available && reproducibility.data.check ? (
        <Panel
          title="Reproducibility"
          description="The pipeline was run twice from the same seed and the metrics compared."
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

function Recommendation({ outcome, recommended, notes, uncertain, minDetection, maxBurden }: {
  outcome: string;
  recommended: CandidateVerdict | null;
  notes: string[];
  uncertain: string[];
  minDetection: number;
  maxBurden: number;
}) {
  if (!recommended) {
    return (
      <Callout tone="fault" title="No candidate is recommended">
        <p>
          Nothing tested kept {percent(minDetection)} detection under every required sensor fault while staying within a{" "}
          {percent(maxBurden)} alarm burden. This is a result, not a failure of the tool: deploying any of these on this
          data would mean accepting alerts that disappear when a sensor does.
        </p>
        {notes.length > 0 ? (
          <ul>
            {notes.map(note => (<li key={note}>{note}</li>))}
          </ul>
        ) : null}
      </Callout>
    );
  }

  // Overlapping intervals do not establish a reliable ranking.
  const contested = uncertain.length > 0;
  const drop = recommended.clean.detection_fraction - recommended.worst_detection_required;

  return (
    <Callout tone={contested ? "warn" : "ok"}>
      <h3>
        {contested ? "Recommended, but not clearly ahead" : "Recommended"}:{" "}
        {candidateLabel(recommended.candidate, recommended.config_id)}
      </h3>
      <p>
        It keeps {percent(recommended.worst_detection_required, 1)} detection in its worst required fault scenario
        {recommended.worst_scenario_id ? (
          <>
            {" "}
            (<span className="mono">{recommended.worst_scenario_id}</span>)
          </>
        ) : null}
        , against {percent(recommended.clean.detection_fraction, 1)} on undamaged readings, a drop of{" "}
        {number(drop * 100, 1)} percentage points. Median warning is {cycles(recommended.clean.median_lead_time)} before
        failure, at an alarm burden of {percent(recommended.clean.early_alarm_burden, 1)}. Passing required scenarios:{" "}
        {integer(recommended.required_passed)} of {integer(recommended.required_scenarios)}.
      </p>
      {[...notes, ...uncertain].length > 0 ? (
        <details>
          <summary>Why the ranking remains uncertain</summary>
          <p className="note">
            The clean-data detection intervals overlap. A paired analysis of fault outcomes would be needed to establish
            whether the leading candidates differ.
          </p>
          <ul>
            {[...notes, ...uncertain].map(note => (<li key={note}>{note}</li>))}
          </ul>
        </details>
      ) : null}
      {outcome === "qualified" ? null : (
        <p className="note" style={{ margin: 0 }}>
          Selection outcome recorded as <span className="mono">{outcome}</span>.
        </p>
      )}
    </Callout>
  );
}

function FailureDetail({ verdict, minDetection }: { verdict: CandidateVerdict; minDetection: number }) {
  const failing = verdict.failing_scenarios ?? [];

  return (
    <Panel
      title="Outcome breakdown"
      description="Out-of-fold development outcomes on the original readings, followed by required cases that failed a detection or alarm-burden limit."
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
          note="no useful or late warning; an early-only alarm may still have occurred"
        />
        <Stat
          label="New alerts"
          value={number(verdict.clean.new_episodes_per_1000, 1)}
          note={`per 1000 eligible early-life cycles, at threshold ${number(verdict.threshold, 3)}`}
        />
      </div>

      {failing.length > 0 ? (
        <>
          <p className="note" style={{ marginBottom: 6 }}>
            Required scenarios failing the {percent(minDetection)} detection minimum or the alarm-burden limit:
          </p>
          <div className="pill-row">
            {failing.map((scenario: string) => (
              <span className="tool-chip failed" key={scenario}>
                {scenario}
              </span>
            ))}
          </div>
        </>
      ) : null}
    </Panel>
  );
}
