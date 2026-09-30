import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import type { ReplaySeries } from "../api/types";
import { Badge, Field, Panel, StateBlock } from "../components/Chrome";
import { ContributionBars } from "../components/ContributionBars";
import { ScoreTimeline, SensorTrace } from "../components/ScoreTimeline";
import { candidateLabel, integer, number, scenarioLabel } from "../format";
import { useApi } from "../hooks/useApi";
import { episodeLabel, outcomeLabel } from "../replay";

export function WarningReplay() {
  const api = useEvidence();
  const index = useApi(() => api.replayIndex(), [api]);
  const config = useApi(() => api.config(), [api]);
  const horizon = Number(config.data?.config.horizon_cycles ?? 30);
  const minLead = Number(config.data?.config.min_useful_lead ?? 10);
  const [params, setParams] = useSearchParams();
  const experimentId = useExperimentId();
  const entries = index.data?.series ?? [];
  const requestedEquipment = params.get("equipment");
  const requestedScenario = params.get("scenario");
  const defaultEquipment = !experimentId && index.data?.equipment.includes("13") ? "13" : index.data?.equipment[0] ?? "";
  const equipment = requestedEquipment && index.data?.equipment.includes(requestedEquipment) ? requestedEquipment : defaultEquipment;
  const scenariosFor = useMemo(
    () => [...new Set(entries.filter(e => e.equipment_id === equipment).map(e => e.scenario_id))],
    [entries, equipment]
  );
  const defaultScenario = scenariosFor.find(id => id !== "clean") ?? scenariosFor[0] ?? "";
  const scenario = requestedScenario && scenariosFor.includes(requestedScenario) ? requestedScenario : defaultScenario;
  const invalidSelection = Boolean(index.data && ((requestedEquipment && requestedEquipment !== equipment) || (requestedScenario && requestedScenario !== scenario)));
  function setEquipment(value: string) {
    const next = new URLSearchParams(params);
    next.set("equipment", value);
    const available = entries.filter(e => e.equipment_id === value);
    const nextScenario = available.find(e => e.scenario_id === scenario) ?? available.find(e => e.scenario_id !== "clean") ?? available[0];
    if (nextScenario) next.set("scenario", nextScenario.scenario_id);
    else next.delete("scenario");
    setParams(next);
  }
  function setScenario(value: string) {
    const next = new URLSearchParams(params);
    next.set("equipment", equipment);
    next.set("scenario", value);
    setParams(next);
  }

  const series = useApi(() => (equipment ? api.replay(equipment) : Promise.resolve([])), [api, equipment]);
  const explanations = useApi(() => (equipment ? api.explanations(equipment) : Promise.resolve([])), [api, equipment]);

  const all = series.data ?? [];
  const selected = all.find(s => s.equipment_id === equipment && s.scenario_id === scenario) ?? null;
  const clean = all.find(s => s.equipment_id === equipment && s.scenario_id === "clean" && s.candidate === selected?.candidate && s.config_id === selected?.config_id) ?? null;
  const comparison = selected && selected.scenario_id !== "clean" ? clean : null;

  const explanation = useMemo(() => {
    if (!selected || selected.fault) return null;
    const candidates = (explanations.data ?? []).filter(item => item.equipment_id === selected.equipment_id);
    if (candidates.length === 0) return null;
    const firstEpisode = selected.episodes[0];
    if (!firstEpisode) return candidates[0] ?? null;
    // Pair the explanation with the cycle the alert actually opened on.
    return candidates.find(item => item.cycle === firstEpisode.start_cycle) ?? candidates[0] ?? null;
  }, [explanations.data, selected]);

  return (
    <>
      <header className="page-head">
        <h1>Warning replay</h1>
        <p>
          Compare the same machine with its original readings and an injected sensor fault. Does the warning still arrive in time?
        </p>
      </header>

      {invalidSelection && <p className="note" role="status">That history or scenario is unavailable in this experiment. Showing an available replay instead.</p>}
      <StateBlock loading={index.loading} error={index.error} empty={entries.length === 0}>
        <Panel title="Select a history">
          <div className="controls">
            <Field label="Equipment">
              <select value={equipment} onChange={event => setEquipment(event.target.value)}>
                {(index.data?.equipment ?? []).map(id => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Scenario">
              <select value={scenario} onChange={event => setScenario(event.target.value)}>
                {scenariosFor.map(id => (
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

      <StateBlock loading={series.loading || config.loading} error={series.error || config.error} empty={!selected}>
        {selected ? (
          <>
            <p className="note">
              Replaying {candidateLabel(selected.candidate, selected.config_id)}, equipment {equipment}, failure at cycle {integer(selected.failure_cycle)}. These are recorded development traces; selecting another candidate in comparison does not change this replay model.
            </p>
            <Panel
              title="Score against remaining life"
              description={
                selected.fault
                  ? `Read left to right towards failure. The red line is the score with ${selected.fault.sensor} ${describeFault(selected.fault)}; the dashed blue line is the same history with the sensor intact.`
                  : "Read left to right towards failure. A warning is useful if the alert is active at any point inside the shaded window."
              }
            >
              {comparison && (
                <dl className="replay-outcomes">
                  <div><dt>Original readings</dt><dd><Outcome series={comparison} /></dd></div>
                  <div><dt>With the sensor fault</dt><dd><Outcome series={selected} /></dd></div>
                  <div><dt>Warning change</dt><dd>{warningChange(comparison, selected)}</dd></div>
                </dl>
              )}
              <ScoreTimeline series={selected} comparison={comparison} horizon={horizon} minLead={minLead} />
            </Panel>

            {selected.fault ? (
              <Panel
                title={`What happened to ${selected.fault.sensor}`}
                description={`The fault begins ${selected.fault_onset_rul ?? "—"} cycles before failure, affects ${selected.fault_affected_cycles} cycles, and is ${selected.fault.duration === "persistent" ? "never repaired" : "repaired after a short burst"}. Features are recomputed from the altered readings before scoring.`}
              >
                <SensorTrace series={selected} />
              </Panel>
            ) : null}

            <Panel title="Alert episodes" tight>
              {selected.episodes.length === 0 ? (
                <p className="note">
                  The score never stayed above {number(selected.threshold, 3)} for two consecutive cycles, so no alert
                  was ever raised for this history.
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
                      {selected.episodes.map(episode => (
                        <tr key={`${episode.start_cycle}-${episode.end_cycle}`}>
                          <td className="num">{integer(episode.start_cycle)}</td>
                          <td className="num">{integer(episode.start_rul)}</td>
                          <td className="num">{integer(episode.end_cycle)}</td>
                          <td className="num">{integer(episode.end_cycle - episode.start_cycle + 1)}</td>
                          <td className="num">{number(episode.peak_score, 3)}</td>
                          <td>{episodeLabel(episode, horizon, minLead)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            {selected.fault ? (
              <p className="note">
                Feature contributions are available for the original readings only. Switch to the clean scenario to
                inspect them.
              </p>
            ) : null}
            {explanation ? (
              <Panel
                title="What moved the score"
                description={`Feature contributions at cycle ${explanation.cycle}. This describes how the model reached its number; it is not a diagnosis of the machine.`}
                tight
              >
                <div className="table-scroll">
                  <ContributionBars explanation={explanation} />
                </div>
              </Panel>
            ) : null}
          </>
        ) : null}
      </StateBlock>
    </>
  );
}

function Outcome({ series }: { series: ReplaySeries }) {
  const label = outcomeLabel(series.outcome);
  return <Badge tone={label.tone}>{label.text}</Badge>;
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

function warningChange(clean: ReplaySeries, faulted: ReplaySeries): string {
  if (clean.outcome.detected && !faulted.outcome.detected) return faulted.outcome.late ? "Useful warning became late" : "Useful warning was missed";
  if (!clean.outcome.detected && faulted.outcome.detected) return "Useful warning gained";
  const before = clean.outcome.lead_time;
  const after = faulted.outcome.lead_time;
  if (!clean.outcome.detected || !faulted.outcome.detected || before == null || after == null) return "No useful lead-time comparison";
  const change = after - before;
  return change === 0 ? "Same lead time" : `${Math.abs(change)} cycles ${change > 0 ? "longer" : "shorter"}`;
}
