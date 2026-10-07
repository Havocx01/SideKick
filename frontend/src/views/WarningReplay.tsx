import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import { Panel, StateBlock } from "../components/Chrome";
import { ContributionBars } from "../components/ContributionBars";
import { ReplayExample } from "../components/ReplayExample";
import { candidateLabel, integer, number, scenarioLabel } from "../format";
import { useApi } from "../hooks/useApi";
import { episodeLabel } from "../replay";
import { Combobox } from "@/registry/components/combobox/combobox";

export function WarningReplay() {
  const api = useEvidence();
  const index = useApi(() => api.replayIndex(), [api]);
  const config = useApi(() => api.config(), [api]);
  const selection = useApi(() => api.selection(), [api]);
  const horizon = Number(config.data?.config.horizon_cycles ?? 30);
  const minLead = Number(config.data?.config.min_useful_lead ?? 10);
  const [params, setParams] = useSearchParams();
  const experimentId = useExperimentId();
  const leader = selection.data?.recommended ?? selection.data?.ranked[0];
  const candidate = params.get("candidate") ?? (leader ? `${leader.candidate}/${leader.config_id}` : "");
  const entries = (index.data?.series ?? []).filter(e => `${e.candidate}/${e.config_id}` === candidate);
  const equipmentIds = [...new Set(entries.map(e => e.equipment_id))];
  const requestedEquipment = params.get("equipment");
  const requestedScenario = params.get("scenario");
  const defaultEquipment = !experimentId && equipmentIds.includes("13") ? "13" : equipmentIds[0] ?? "";
  const equipment = requestedEquipment && equipmentIds.includes(requestedEquipment) ? requestedEquipment : defaultEquipment;
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

  const all = (series.data ?? []).filter(s => `${s.candidate}/${s.config_id}` === candidate);
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
      </header>

      {invalidSelection && <p className="note" role="status">That history or scenario is unavailable in this experiment. Showing an available replay instead.</p>}
      <StateBlock loading={index.loading || selection.loading} error={index.error || selection.error}>
        <Panel title="Select a history">
          <div className="controls">
            <Combobox label="Candidate" required value={candidate} onValueChange={value => { if (value) { const next = new URLSearchParams(params); next.set("candidate", value); next.delete("equipment"); next.delete("scenario"); setParams(next); } }} options={(selection.data?.ranked ?? []).map(v => ({ value: `${v.candidate}/${v.config_id}`, label: candidateLabel(v.candidate, v.config_id) }))} />
            <Combobox label="Equipment" required value={equipment} onValueChange={value => { if (value) setEquipment(value); }} options={equipmentIds.map(value => ({ value, label: `Equipment ${value}` }))} />
            <Combobox label="Scenario" required value={scenario} onValueChange={value => { if (value) setScenario(value); }} options={scenariosFor.map(value => ({ value, label: scenarioLabel(value) }))} />
          </div>
          {!entries.length && <p className="note">No representative replay is stored for this candidate and partition. Inspect its comparison or select another candidate.</p>}
        </Panel>
      </StateBlock>

      <StateBlock loading={series.loading || config.loading} error={series.error || config.error} empty={!selected}>
        {selected ? (
          <>
            <ReplayExample series={selected} comparison={comparison} horizon={horizon} minLead={minLead} />
            <details className="disclosure disclosure-plain"><summary>Replay source and alert episodes</summary>
            <p className="note">{candidateLabel(selected.candidate, selected.config_id)} · Equipment {equipment} · Failure at cycle {integer(selected.failure_cycle)}. {selected.representative_reason || "One selected example, not fleet-wide performance."}</p>
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
            </details>
            {explanation ? (
              <details className="disclosure"><summary>Feature contributions</summary>
              <Panel
                title="What moved the score"
                description={`Feature contributions at cycle ${explanation.cycle}. Model explanation, not a physical diagnosis.`}
                tight
              >
                <div className="table-scroll">
                  <ContributionBars explanation={explanation} />
                </div>
              </Panel>
              </details>
            ) : null}
          </>
        ) : null}
      </StateBlock>
    </>
  );
}
