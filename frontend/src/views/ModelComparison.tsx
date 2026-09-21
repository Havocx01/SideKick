import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { CandidateVerdict } from "../api/types";
import { Badge, Callout, Panel, StateBlock, Stat } from "../components/Chrome";
import { IntervalBar } from "../components/IntervalBar";
import { ReliabilityPlot } from "../components/ReliabilityPlot";
import { ScenarioHeatmap } from "../components/ScenarioHeatmap";
import { candidateKey, candidateLabel, cycles, integer, interval, number, percent } from "../format";
import { useApi } from "../hooks/useApi";

/**
 * The recommendation and the evidence behind it.
 *
 * Ordered by worst-case detection rather than clean-data performance, because the
 * ranking that changes when faults are applied is the result worth showing. The
 * leaderboard exists to make disagreement with the recommendation possible.
 */
export function ModelComparison() {
  const selection = useApi(() => api.selection(), []);
  const final = useApi(() => api.finalEvaluation(), []);
  const calibration = useApi(() => api.calibration(), []);
  const reproducibility = useApi(() => api.reproducibility(), []);

  const [focus, setFocus] = useState<string | null>(null);

  const criteria = selection.data?.criteria;
  const verdicts = useMemo(() => selection.data?.ranked ?? [], [selection.data]);

  const focused = focus
    ? verdicts.find((verdict) => candidateKey(verdict.candidate, verdict.config_id) === focus)
    : verdicts[0];

  // Fetched per candidate rather than all at once: the whole matrix is several
  // megabytes, and the heatmap only ever shows one candidate.
  const focusKey = focused ? candidateKey(focused.candidate, focused.config_id) : "";
  const scenarios = useApi(
    () => (focusKey ? api.scenarios({ candidate: focusKey, includeClean: false }) : Promise.resolve([])),
    [focusKey],
  );
  const focusedScenarios = scenarios.data ?? [];

  return (
    <>
      <header className="page-head">
        <h1>Model comparison</h1>
        <p>
          Candidates ranked by the detection rate they keep when a sensor fails, not by their
          performance on undamaged readings. Where those two orderings disagree, the second one is
          the one that predicts field behaviour.
        </p>
      </header>

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
                  Worst case is the weakest result across the {integer(
                    verdicts[0]?.required_scenarios ?? 0,
                  )}{" "}
                  required fault scenarios. Bars show the 95% interval; a wide bar means the
                  held-out data cannot separate these candidates, and reading the point estimates
                  as a ranking would overstate what was measured.
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
                    {verdicts.map((verdict) => {
                      const key = candidateKey(verdict.candidate, verdict.config_id);
                      const isFocus = focused
                        ? key === candidateKey(focused.candidate, focused.config_id)
                        : false;
                      const isRecommended =
                        selection.data?.recommended?.candidate === verdict.candidate &&
                        selection.data?.recommended?.config_id === verdict.config_id;
                      const drop = verdict.clean.detection_fraction - verdict.worst_detection_required;
                      return (
                        <tr
                          key={key}
                          onClick={() => setFocus(key)}
                          className={isFocus ? "row-focus" : undefined}
                          style={{ cursor: "pointer" }}
                        >
                          <td>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span>{candidateLabel(verdict.candidate, verdict.config_id)}</span>
                              {isRecommended ? <Badge tone="ok">recommended</Badge> : null}
                              {verdict.candidate === "age_baseline" ? (
                                <Badge tone="neutral">no sensors</Badge>
                              ) : null}
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
                            {verdict.worst_metrics
                              ? percent(verdict.worst_metrics.detection_fraction, 1)
                              : "—"}
                          </td>
                          <td className="num">
                            {verdict.worst_metrics ? (
                              <span
                                style={{
                                  color: drop > 0.15 ? "var(--fault)" : "var(--ink-soft)",
                                }}
                              >
                                {drop > 0 ? "−" : ""}
                                {percent(Math.abs(drop), 1)}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="num">
                            {percent(verdict.clean.early_alarm_burden, 1)}
                          </td>
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
                Burden is the share of alarm-free cycles spent in alarm, excluding the transition
                band. Lead is the median cycles of warning before failure. Select a row to see its
                fault detail below.
              </p>
            </Panel>

            {focused ? (
              <>
                <Panel
                  title={`Where ${candidateLabel(focused.candidate, focused.config_id)} breaks`}
                  description="Every fault scenario tested, as the sensor that failed against how it failed. One dark row means a single channel this candidate depends on; a dark column means a failure mode it cannot tolerate on any channel."
                  aside={
                    <div className="pill-row">
                      {verdicts.map((verdict) => {
                        const key = candidateKey(verdict.candidate, verdict.config_id);
                        const active = key === candidateKey(focused.candidate, focused.config_id);
                        return (
                          <button
                            key={key}
                            onClick={() => setFocus(key)}
                            className={active ? "active" : undefined}
                          >
                            {candidateLabel(verdict.candidate, verdict.config_id)}
                          </button>
                        );
                      })}
                    </div>
                  }
                >
                  <StateBlock
                    loading={scenarios.loading}
                    error={scenarios.error}
                    empty={focusedScenarios.length === 0}
                  >
                    <ScenarioHeatmap
                      results={focusedScenarios}
                      minDetection={criteria.min_detection_fraction}
                    />
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
          description="Scored once, on machines no model or threshold ever saw, after the configuration was frozen. Development numbers above guided the choice; this is the number that estimates field behaviour."
        >
          {final.data.available && final.data.selection?.recommended ? (
            <div className="grid cols-3" style={{ marginBottom: 0 }}>
              <Stat
                label="Detection, clean"
                value={percent(final.data.selection.recommended.clean.detection_fraction, 1)}
                note={interval(
                  final.data.selection.recommended.clean.detection_ci.lower,
                  final.data.selection.recommended.clean.detection_ci.upper,
                )}
              />
              <Stat
                label="Detection, worst fault"
                value={percent(final.data.selection.recommended.worst_detection_required, 1)}
                note={final.data.selection.recommended.worst_scenario_id ?? "—"}
              />
              <Stat
                label="Median lead"
                value={cycles(final.data.selection.recommended.clean.median_lead_time)}
                note="cycles of warning before failure"
              />
            </div>
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
              <Badge tone="bad">
                differs by {number(reproducibility.data.check.max_absolute_difference, 6)}
              </Badge>
            )}
            <span className="note">
              {integer(reproducibility.data.check.metrics_compared)} metrics compared between{" "}
              <span className="mono">{reproducibility.data.check.run_id}</span> and{" "}
              <span className="mono">{reproducibility.data.check.repeat_run_id}</span>, to a
              tolerance of {number(reproducibility.data.check.tolerance, 9)}
            </span>
          </div>
        </Panel>
      ) : null}
    </>
  );
}

function Recommendation({
  outcome,
  recommended,
  notes,
  uncertain,
  minDetection,
  maxBurden,
}: {
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
          Nothing tested kept {percent(minDetection)} detection under every required sensor fault
          while staying within a {percent(maxBurden)} alarm burden. This is a result, not a failure
          of the tool: deploying any of these on this data would mean accepting alerts that
          disappear when a sensor does.
        </p>
        {notes.length > 0 ? (
          <ul>
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        ) : null}
      </Callout>
    );
  }

  // An overlapping interval means the ranking is not established by the data, so
  // the heading is softened rather than leaving a confident claim in place.
  const contested = uncertain.length > 0;
  const drop = recommended.clean.detection_fraction - recommended.worst_detection_required;

  return (
    <Callout tone={contested ? "warn" : "ok"}>
      <h3>
        {contested ? "Recommended, but not clearly ahead" : "Recommended"}:{" "}
        {candidateLabel(recommended.candidate, recommended.config_id)}
      </h3>
      <p>
        It keeps {percent(recommended.worst_detection_required, 1)} detection in its worst required
        fault scenario
        {recommended.worst_scenario_id ? (
          <>
            {" "}
            (<span className="mono">{recommended.worst_scenario_id}</span>)
          </>
        ) : null}
        , against {percent(recommended.clean.detection_fraction, 1)} on undamaged readings — a drop
        of {percent(drop, 1)}. Median warning is {cycles(recommended.clean.median_lead_time)} cycles
        before failure, at an alarm burden of {percent(recommended.clean.early_alarm_burden, 1)}.
        Passing required scenarios: {integer(recommended.required_passed)} of{" "}
        {integer(recommended.required_scenarios)}.
      </p>
      {[...notes, ...uncertain].length > 0 ? (
        <ul>
          {[...notes, ...uncertain].map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {outcome === "qualified" ? null : (
        <p className="note" style={{ margin: 0 }}>
          Selection outcome recorded as <span className="mono">{outcome}</span>.
        </p>
      )}
    </Callout>
  );
}

/** The numbers behind one candidate's verdict, including what it misses. */
function FailureDetail({
  verdict,
  minDetection,
}: {
  verdict: CandidateVerdict;
  minDetection: number;
}) {
  const failing = verdict.failing_scenarios ?? [];

  return (
    <Panel
      title="Outcome breakdown"
      description="How the held-out histories resolved on undamaged readings, and which required scenarios fell below the minimum."
    >
      <div className="grid cols-4" style={{ marginBottom: failing.length > 0 ? 14 : 0 }}>
        <Stat
          label="Warned in time"
          value={`${integer(verdict.clean.detected)} / ${integer(verdict.clean.engines)}`}
          note={`${percent(verdict.clean.detection_fraction, 1)} of histories`}
        />
        <Stat
          label="Warned too late"
          value={integer(verdict.clean.late)}
          note="alert opened inside the final cycles"
        />
        <Stat
          label="No warning"
          value={integer(verdict.clean.missed)}
          note="failed without an alert"
        />
        <Stat
          label="New alerts"
          value={number(verdict.clean.new_episodes_per_1000, 1)}
          note={`per 1000 alarm-free cycles, at threshold ${number(verdict.threshold, 3)}`}
        />
      </div>

      {failing.length > 0 ? (
        <>
          <p className="note" style={{ marginBottom: 6 }}>
            Required scenarios below {percent(minDetection)} detection:
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
