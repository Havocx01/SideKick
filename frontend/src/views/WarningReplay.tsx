import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { ReplaySeries } from "../api/types";
import { Badge, Field, Panel, StateBlock } from "../components/Chrome";
import { ContributionBars } from "../components/ContributionBars";
import { ScoreTimeline, SensorTrace } from "../components/ScoreTimeline";
import { cycles, integer, number, scenarioLabel } from "../format";
import { useApi } from "../hooks/useApi";

/**
 * One machine, one history, cycle by cycle.
 *
 * The comparison view answers which model to deploy; this one answers whether to
 * believe it. Aggregate detection rates hide whether a warning arrived with enough
 * time to act, and whether the same warning still arrives when a sensor fails, so
 * the clean and faulted runs are drawn on one axis rather than side by side.
 */
export function WarningReplay() {
  const index = useApi(() => api.replayIndex(), []);
  const [equipment, setEquipment] = useState<string>("");
  const [scenario, setScenario] = useState<string>("");

  const entries = index.data?.series ?? [];

  useEffect(() => {
    if (!equipment && index.data?.equipment.length) {
      setEquipment(index.data.equipment[0] ?? "");
    }
  }, [index.data, equipment]);

  const scenariosFor = useMemo(
    () =>
      [...new Set(entries.filter((e) => e.equipment_id === equipment).map((e) => e.scenario_id))],
    [entries, equipment],
  );

  useEffect(() => {
    if (scenariosFor.length > 0 && !scenariosFor.includes(scenario)) {
      // Prefer a fault scenario, since the clean run is drawn alongside it anyway.
      setScenario(scenariosFor.find((id) => id !== "clean") ?? scenariosFor[0] ?? "");
    }
  }, [scenariosFor, scenario]);

  const series = useApi(
    () => (equipment ? api.replay(equipment) : Promise.resolve([])),
    [equipment],
  );
  const explanations = useApi(
    () => (equipment ? api.explanations(equipment) : Promise.resolve([])),
    [equipment],
  );

  const all = series.data ?? [];
  const selected = all.find((s) => s.scenario_id === scenario) ?? all[0] ?? null;
  const clean = all.find((s) => s.scenario_id === "clean") ?? null;
  const comparison = selected && selected.scenario_id !== "clean" ? clean : null;

  const explanation = useMemo(() => {
    if (!selected) return null;
    const candidates = (explanations.data ?? []).filter(
      (item) => item.equipment_id === selected.equipment_id,
    );
    if (candidates.length === 0) return null;
    const firstEpisode = selected.episodes[0];
    if (!firstEpisode) return candidates[0] ?? null;
    // Pair the explanation with the cycle the alert actually opened on.
    return (
      candidates.find((item) => item.cycle === firstEpisode.start_cycle) ?? candidates[0] ?? null
    );
  }, [explanations.data, selected]);

  return (
    <>
      <header className="page-head">
        <h1>Warning replay</h1>
        <p>
          One machine's history as the model saw it, cycle by cycle. The same history is shown with
          a sensor fault injected, so the question is not whether detection fell on average but
          whether this warning still arrives.
        </p>
      </header>

      <StateBlock loading={index.loading} error={index.error} empty={entries.length === 0}>
        <Panel title="Select a history" tight>
          <div className="controls">
            <Field label="Equipment">
              <select value={equipment} onChange={(event) => setEquipment(event.target.value)}>
                {(index.data?.equipment ?? []).map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Scenario">
              <select value={scenario} onChange={(event) => setScenario(event.target.value)}>
                {scenariosFor.map((id) => (
                  <option key={id} value={id}>
                    {scenarioLabel(id)}
                  </option>
                ))}
              </select>
            </Field>
            {selected ? (
              <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "flex-end" }}>
                <Outcome series={selected} />
              </div>
            ) : null}
          </div>
        </Panel>
      </StateBlock>

      <StateBlock loading={series.loading} error={series.error} empty={!selected}>
        {selected ? (
          <>
            <Panel
              title="Score against remaining life"
              description={
                selected.fault
                  ? `Read right to left towards failure. The red line is the score with ${selected.fault.sensor} ${describeFault(selected.fault)}; the faint blue line is the same history with the sensor intact.`
                  : "Read right to left towards failure. A warning is useful if the alert opens inside the shaded window."
              }
            >
              <ScoreTimeline series={selected} comparison={comparison} />
            </Panel>

            {selected.fault ? (
              <Panel
                title={`What happened to ${selected.fault.sensor}`}
                description={`The fault begins ${selected.fault_onset_rul ?? "—"} cycles before failure, affects ${selected.fault_affected_cycles} cycles, and is ${selected.fault.duration === "persistent" ? "never repaired" : "repaired after a short burst"}. Features are recomputed from the altered readings, so the model sees exactly what a field system would.`}
                tight
              >
                <SensorTrace series={selected} />
              </Panel>
            ) : null}

            <Panel title="Alert episodes" tight>
              {selected.episodes.length === 0 ? (
                <p className="note">
                  The score never stayed above {number(selected.threshold, 3)} for two consecutive
                  cycles, so no alert was ever raised for this history.
                </p>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th className="num">Opened at cycle</th>
                        <th className="num">Cycles remaining</th>
                        <th className="num">Closed at cycle</th>
                        <th className="num">Cycles in alarm</th>
                        <th className="num">Peak score</th>
                        <th>Would this have helped?</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.episodes.map((episode) => (
                        <tr key={`${episode.start_cycle}-${episode.end_cycle}`}>
                          <td className="num">{integer(episode.start_cycle)}</td>
                          <td className="num">{integer(episode.start_rul)}</td>
                          <td className="num">{integer(episode.end_cycle)}</td>
                          <td className="num">
                            {integer(episode.end_cycle - episode.start_cycle + 1)}
                          </td>
                          <td className="num">{number(episode.peak_score, 3)}</td>
                          <td>{judgeEpisode(episode.start_rul)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            {explanation ? (
              <Panel
                title="What moved the score"
                description={`Feature contributions at cycle ${explanation.cycle}. This describes how the model reached its number; it is not a diagnosis of the machine.`}
                tight
              >
                <ContributionBars explanation={explanation} />
              </Panel>
            ) : null}
          </>
        ) : null}
      </StateBlock>
    </>
  );
}

function Outcome({ series }: { series: ReplaySeries }) {
  const first = series.episodes[0];
  if (!first) return <Badge tone="bad">no warning</Badge>;
  if (first.start_rul <= 9) return <Badge tone="warn">warned too late</Badge>;
  if (first.start_rul > 30) {
    return (
      <>
        <Badge tone="info">alert opened early</Badge>
        <Badge tone="ok">warned {cycles(first.start_rul)} ahead</Badge>
      </>
    );
  }
  return <Badge tone="ok">warned {cycles(first.start_rul)} ahead</Badge>;
}

function judgeEpisode(startRul: number): JSX.Element {
  if (startRul > 45) return <span className="note">before the warning horizon</span>;
  if (startRul > 30) return <span className="note">in the transition band</span>;
  if (startRul >= 10) return <Badge tone="ok">actionable warning</Badge>;
  return <Badge tone="warn">too late to act</Badge>;
}

function describeFault(fault: NonNullable<ReplaySeries["fault"]>): string {
  switch (fault.kind) {
    case "dropout":
      return "reporting nothing";
    case "stuck":
      return "frozen at its last value";
    case "drift":
      return `drifting ${fault.sign && fault.sign < 0 ? "down" : "up"} by ${number(fault.severity_sd, 1)} standard deviations`;
    default:
      return "faulted";
  }
}
