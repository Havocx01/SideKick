import { useEffect, useState } from "react";
import { useIsPresent, useReducedMotion } from "motion/react";
import { useSearchParams } from "react-router-dom";
import type { ReplaySeries } from "../api/types";
import { useAnalysis } from "./AnalysisProvider";
import { useExperimentId } from "../hooks/useEvidence";
import { Badge, Button, IconButton, Panel } from "./Chrome";
import { Pause, Play, RotateCcw } from "lucide-react";
import { ScoreTimeline, SensorTrace } from "./ScoreTimeline";
import { ReplaySlider } from "./ReplaySlider";
import { outcomeLabel } from "../replay";
import { integer } from "../format";

interface ReplayExampleProps { series: ReplaySeries; comparison?: ReplaySeries | null; horizon: number; minLead: number; guided?: boolean }

export function ReplayExample(props: ReplayExampleProps) {
  const s = props.series;
  return <Player key={`${s.partition}/${s.candidate}/${s.config_id}/${s.equipment_id}/${s.scenario_id}`} {...props} />;
}

function Player({ series, comparison, horizon, minLead, guided = false }: ReplayExampleProps) {
  const reduced = useReducedMotion();
  const present = useIsPresent();
  const analysis = useAnalysis();
  const experimentId = useExperimentId();
  const last = Math.max(0, series.points.length - 1);
  const [params] = useSearchParams();
  const requestedCycle = params.get("cycle");
  const requestedIndex = requestedCycle === null ? -1 : series.points.findIndex(p => String(p.cycle) === requestedCycle);
  const [index, setIndex] = useState(requestedIndex >= 0 ? requestedIndex : last);
  useEffect(() => { if (requestedIndex >= 0) { setPlaying(false); setIndex(requestedIndex); } }, [requestedIndex]);
  const [playing, setPlaying] = useState(false);
  useEffect(() => { if (!present) setPlaying(false); }, [present]);
  const point = series.points[index];
  const original = comparison?.points.find(p => p.cycle === point?.cycle);
  const faultIndex = series.fault && series.fault_onset_rul != null && (series.points[0]?.rul ?? -1) >= series.fault_onset_rul
    ? series.points.findIndex(p => p.rul <= series.fault_onset_rul!) : -1;
  const windowIndex = series.points.findIndex(p => p.rul <= horizon && p.rul >= minLead);
  useEffect(() => { if (guided && reduced) setPlaying(false); }, [guided, reduced]);
  useEffect(() => {
    if (!playing || last < 1) return;
    let frame = 0;
    let started: number | null = null;
    const first = index;
    function advance(now: number) {
      started ??= now;
      const next = Math.min(last, first + Math.floor((now - started) / 20_000 * last));
      setIndex(next);
      if (next === last) setPlaying(false);
      else frame = requestAnimationFrame(advance);
    }
    frame = requestAnimationFrame(advance);
    return () => cancelAnimationFrame(frame);
  }, [playing, last]);
  useEffect(() => {
    const pause = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener("visibilitychange", pause);
    return () => document.removeEventListener("visibilitychange", pause);
  }, []);
  if (!point) return <p className="state">This history has no stored cycles to replay.</p>;
  const outcome = outcomeLabel(series.outcome);
  const cleanOutcome = comparison ? outcomeLabel(comparison.outcome) : null;
  const warningState = (alert: boolean) => guided ? (alert ? "Warning on" : "Warning off") : (alert ? "Warning active" : "Warning inactive");
  const window = point.rul >= minLead && point.rul <= horizon ? "Useful window" : point.rul > horizon ? "Before window" : "After window";
  const historyResults = <dl className="replay-outcomes" aria-label="Whole-history results">
    {cleanOutcome && <div><dt>Original · Whole history</dt><dd><Badge tone={cleanOutcome.tone}>{cleanOutcome.text}</Badge></dd></div>}
    <div><dt>{series.fault ? "Faulted" : "Original"} · Whole history</dt><dd><Badge tone={outcome.tone}>{outcome.text}</Badge></dd></div>
  </dl>;
  const sensorReadings = series.fault && <Panel title={`What happened to ${series.fault.sensor}`} description={`Fault starts ${series.fault_onset_rul ?? "an unrecorded number of"} cycles before failure · ${series.fault.duration === "persistent" ? "Persistent" : "Temporary"}`}>
    <SensorTrace series={series} cursorCycle={point.cycle} />
  </Panel>;
  return <>
    <Panel title="When the warning appears" description="Playback of stored results" aside={!guided && analysis.enabled("warning") && <Button variant="secondary" onClick={() => { setPlaying(false); analysis.start({ task: "warning", experiment_id: experimentId, partition: series.partition, candidates: [`${series.candidate}/${series.config_id}`], equipment_id: series.equipment_id, scenario_id: series.scenario_id, cycle: point.cycle }); }}>Explain warning</Button>}>
      {!guided && historyResults}
      <div className="playback-controls">
        <div className="playback-buttons">
          <IconButton label={playing ? "Pause" : index === last ? "Replay from start" : "Play"} variant="secondary" disabled={last < 1 || (guided && !!reduced)} onClick={() => { if (index === last) setIndex(0); setPlaying(value => !value); }}>{playing ? <Pause size={17} aria-hidden="true" /> : <Play size={17} aria-hidden="true" />}</IconButton>
          <IconButton label="Restart playback" disabled={last < 1} onClick={() => { setPlaying(false); setIndex(0); }}><RotateCcw size={17} aria-hidden="true" /></IconButton>
          {(guided || faultIndex >= 0) && <Button size="sm" variant="ghost" disabled={faultIndex < 0} onClick={() => { setPlaying(false); setIndex(faultIndex); }}>{guided ? "Fault begins" : "Jump to fault"}</Button>}
          {guided && <Button size="sm" variant="ghost" disabled={windowIndex < 0} onClick={() => { setPlaying(false); setIndex(windowIndex); }}>Warning window</Button>}
        </div>
        <ReplaySlider label="Replay cycle" min={0} max={Math.max(1, last)} step={1} value={[index]} disabled={last < 1}
          valueText={`Cycle ${point.cycle}; ${point.rul} cycles before documented failure`}
          onValueChange={values => { setPlaying(false); setIndex(values[0] ?? 0); }} />
        <span className="playback-cycle">Cycle {integer(point.cycle)} / {integer(series.failure_cycle)}</span>
      </div>
      <div className="playback-readout" aria-label="Current replay state">
        <span>{!guided && "Current reading: "}<strong>{integer(point.rul)}</strong> {point.rul === 1 ? "cycle" : "cycles"} before failure · {window}</span>
        <div className="current-alerts">{original && <span>Original <Badge tone={original.alert ? "info" : "neutral"}>{warningState(original.alert)}</Badge></span>}<span>{series.fault ? "Faulted" : "Original"} <Badge tone={point.alert ? "info" : "neutral"}>{warningState(point.alert)}</Badge></span></div>
      </div>
      <div className={guided ? "guided-replay-chart" : undefined}><ScoreTimeline series={series} comparison={comparison} horizon={horizon} minLead={minLead} cursorCycle={point.cycle} compact={guided} height={guided ? 160 : undefined} /></div>
      {guided && <div className="guided-replay-context">
        <p data-testid="replay-guidance">{point.rul >= minLead && point.rul <= horizon
          ? "Warnings count as in time here. Compare the original and faulted warning states."
          : point.rul < minLead ? "New warnings here are too late for the useful warning window."
            : faultIndex >= 0 && index >= faultIndex ? "The sensor fault has begun. Watch how the warning changes as failure gets closer."
              : "The useful warning window is still ahead. Compare the two readings as the history advances."}</p>
        {(faultIndex < 0 || windowIndex < 0) && <p className="note">{faultIndex < 0 ? "Fault onset is not available in this stored trace. " : ""}{windowIndex < 0 ? "No stored reading falls inside the warning window." : ""}</p>}
        {reduced && <p className="note">Reduced motion is on. Use the slider or jump controls.</p>}
      </div>}
      <details><summary>How to read this replay</summary><p className="note">Scores rank risk; they are not necessarily failure probabilities. The shaded window marks useful warning time. Warning state follows the stored alert rule, so one threshold crossing may not activate or clear a warning. One stored example, not fleet-wide performance.</p>{guided && <><p className="note">Alert threshold: {series.threshold.toFixed(3)}</p>{historyResults}{sensorReadings}</>}</details>
    </Panel>
    {!guided && sensorReadings}
  </>;
}
