import { useEffect, useState } from "react";
import type { ReplaySeries } from "../api/types";
import { Badge, Button, Panel } from "./Chrome";
import { ScoreTimeline, SensorTrace } from "./ScoreTimeline";
import { ReplaySlider } from "./ReplaySlider";
import { outcomeLabel } from "../replay";
import { integer } from "../format";

export function ReplayExample(props: { series: ReplaySeries; comparison?: ReplaySeries | null; horizon: number; minLead: number }) {
  const s = props.series;
  return <Player key={`${s.partition}/${s.candidate}/${s.config_id}/${s.equipment_id}/${s.scenario_id}`} {...props} />;
}

function Player({ series, comparison, horizon, minLead }: { series: ReplaySeries; comparison?: ReplaySeries | null; horizon: number; minLead: number }) {
  const last = Math.max(0, series.points.length - 1);
  const [index, setIndex] = useState(last);
  const [playing, setPlaying] = useState(false);
  const point = series.points[index];
  const original = comparison?.points.find(p => p.cycle === point?.cycle);
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
  const window = point.rul >= minLead && point.rul <= horizon ? "Inside the useful warning window" : point.rul > horizon ? "Before the useful warning window" : "After the useful warning window";
  return <>
    <Panel title="Score against remaining life" description="Playback of stored results">
      <dl className="replay-outcomes" aria-label="Whole-history results">
        {cleanOutcome && <div><dt>Original readings, whole history</dt><dd><Badge tone={cleanOutcome.tone}>{cleanOutcome.text}</Badge></dd></div>}
        <div><dt>{series.fault ? "Faulted readings" : "Original readings"}, whole history</dt><dd><Badge tone={outcome.tone}>{outcome.text}</Badge></dd></div>
      </dl>
      <div className="playback-controls">
        <div className="playback-buttons">
          <Button disabled={last < 1} onClick={() => { if (index === last) setIndex(0); setPlaying(value => !value); }}>{playing ? "Pause" : "Play"}</Button>
          <Button variant="ghost" disabled={last < 1} onClick={() => { setPlaying(false); setIndex(0); }}>Restart playback</Button>
        </div>
        <ReplaySlider label="Replay cycle" min={0} max={Math.max(1, last)} step={1} value={[index]} disabled={last < 1}
          valueText={`Cycle ${point.cycle}; ${point.rul} cycles before documented failure`}
          onValueChange={values => { setPlaying(false); setIndex(values[0] ?? 0); }} />
        <span className="playback-cycle">Cycle {integer(point.cycle)} / {integer(series.failure_cycle)}</span>
      </div>
      <div className="playback-readout" aria-label="Current replay state">
        <span>{integer(point.rul)} cycles before documented failure · {window}</span>
        <span>{original ? `Original warning: ${original.alert ? "active" : "inactive"}. ` : ""}{series.fault ? "Faulted warning" : "Warning"}: {point.alert ? "active" : "inactive"}.</span>
      </div>
      <ScoreTimeline series={series} comparison={comparison} horizon={horizon} minLead={minLead} cursorCycle={point.cycle} />
      <p className="note">The score ranks warning risk; it is not necessarily a calibrated failure probability. The shaded window marks useful warning time. This selected example does not describe every history.</p>
    </Panel>
    {series.fault && <Panel title={`What happened to ${series.fault.sensor}`} description={`The simulated fault starts ${series.fault_onset_rul ?? "an unrecorded number of"} cycles before failure. ${series.fault.duration === "persistent" ? "It remains for the rest of this history." : "It is repaired after a short burst."}`}>
      <SensorTrace series={series} cursorCycle={point.cycle} />
    </Panel>}
  </>;
}
