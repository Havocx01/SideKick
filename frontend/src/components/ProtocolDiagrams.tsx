import { useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import SegmentedControl from "@/components/arc/segmented-control/segmented-control";
import { Alert } from "@/components/arc/alert/alert";
import type { ConfigReport } from "../api/client";
import type { DatasetProfile, SplitAssignment } from "../api/types";
import { integer, number, percent } from "../format";
import { protocolTiming, recordedNumber, splitIntegrity, type WarningZone } from "../lib/dataProtocol";
import { Button, Panel } from "./Chrome";
import { ProtocolDisclosure } from "./ProtocolDisclosure";
import styles from "../views/data-protocol.module.css";

export function WarningTiming({ config, positiveFraction }: { config: ConfigReport; positiveFraction?: number | null }) {
  const [zone, setZone] = useState<WarningZone>("timely");
  const [rulesOpen, setRulesOpen] = useState(false);
  const reduced = useReducedMotion();
  const timing = protocolTiming(config.config);
  const selected = timing.zones.find(item => item.id === zone);
  return <Panel title="When a warning counts" description="Operating cycles · Diagram not to scale">
    {timing.available ? <>
      <figure className={styles.warningDiagram} aria-label="Warning timing relative to failure">
        <div className={styles.warningTrack}>
          <svg viewBox="0 0 400 36" role="img" aria-label={`Warning zones: ${timing.zones.map(item => `${item.label}: ${item.range} cycles`).join("; ")}. Failure is at zero cycles. Diagram not to scale.`}>
            {timing.zones.map((item, index) => <g key={item.id}>
              <rect x={index * 100 + 2} y="9" width="94" height="18" rx="4" className={styles[item.id]} />
            </g>)}
            <motion.rect y="32" width="18" height="2" rx="1" fill="var(--text-secondary)" aria-hidden="true" initial={false}
              animate={{ x: timing.zones.findIndex(item => item.id === zone) * 100 + 40 }} transition={{ duration: reduced ? 0 : .2 }} />
          </svg>
          <span className={styles.failureMarker}><i />Failure · 0</span>
        </div>
        <div className={styles.zoneRanges} aria-hidden="true">{timing.zones.map(item => <span key={item.id}>{item.range}</span>)}</div>
      </figure>
      <SegmentedControl label="Warning zone" options={timing.zones.map(item => ({ value: item.id, label: item.label }))} value={zone} onValueChange={value => setZone(value as WarningZone)} />
      <Explanation>{selected?.explanation}</Explanation>
      {timing.gap && <p className={styles.inlineNote}>Cycles {timing.gap} are unscored: outside the recorded useful and late windows.</p>}
    </> : <p className={styles.unavailable}>{timing.note}</p>}
    <ProtocolDisclosure title="Scoring rules" expanded={rulesOpen} onToggle={() => setRulesOpen(value => !value)}>
      <p className={styles.inlineNote}>Recorded rules, fixed before training.</p>
      <dl className={styles.ruleList}>
        <div><dt>Useful warning window</dt><dd>{number(recordedNumber(config.config.min_useful_lead), 0)}–{number(recordedNumber(config.config.horizon_cycles), 0)} cycles before failure</dd></div>
        <div><dt>Late window ends</dt><dd>{number(recordedNumber(config.config.late_window_end), 0)} cycles before failure</dd></div>
        <div><dt>Early-alarm boundary</dt><dd>{number(recordedNumber(config.config.transition_band_end), 0)} cycles before failure</dd></div>
        <div><dt>Alert rule</dt><dd>{number(recordedNumber(config.config.alert_on_consecutive), 0)} consecutive scores at or above threshold to open; {number(recordedNumber(config.config.alert_off_consecutive), 0)} below to close</dd></div>
        <div><dt>Feature window</dt><dd>{number(recordedNumber(config.config.feature_window), 0)} cycles, using current and trailing readings</dd></div>
        <div><dt>Inside the horizon</dt><dd>{percent(positiveFraction, 1)} of scorable cycles labelled positive</dd></div>
        <div><dt>Minimum timely detection</dt><dd>{percent(recordedNumber(config.config.min_detection_fraction), 1)}</dd></div>
        <div><dt>Maximum early-alarm burden</dt><dd>{percent(recordedNumber(config.config.max_early_alarm_burden), 1)}</dd></div>
      </dl>
      <p className={styles.inlineNote}>A history is missed when neither a timely nor a late warning is recorded. Early-alarm burden is the share of eligible cycles spent in warning, not a failure probability. Missing values are shown as —.</p>
    </ProtocolDisclosure>
  </Panel>;
}

export function DataSeparation({ splits, config, profile }: { splits: SplitAssignment; config: ConfigReport | null; profile: DatasetProfile | null }) {
  const [selected, setSelected] = useState<"development" | "reserved">("development");
  const problem = splitIntegrity(splits);
  return <Panel title="How histories stay separate">
    {problem ? <Alert tone="warning" title="Check equipment assignments">{problem}</Alert> : <>
      <figure className={styles.partitionDiagram} aria-label="Dataset separated into development and reserved validation">
        <div className={styles.partitionSource}>Recorded histories{profile && <span> · {integer(profile.equipment_count)} equipment</span>}</div>
        <svg viewBox="0 0 400 30" aria-hidden="true"><path d="M200 0 V8 Q200 15 192 15 H108 Q100 15 100 23 V30 M200 8 Q200 15 208 15 H292 Q300 15 300 23 V30" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" /></svg>
        <div className={styles.partitionBranches} role="group" aria-label="Data partitions">
          <Button className={styles.partitionButton} variant={selected === "development" ? "secondary" : "ghost"} aria-pressed={selected === "development"} onClick={() => setSelected("development")}>
            <span>Development<strong>{integer(splits.development.length)}</strong></span>
          </Button>
          <Button className={styles.partitionButton} variant={selected === "reserved" ? "secondary" : "ghost"} aria-pressed={selected === "reserved"} onClick={() => setSelected("reserved")}>
            <span>Reserved validation<strong>{integer(splits.holdout.length)}</strong></span>
          </Button>
        </div>
      </figure>
      <Explanation>{selected === "development"
        ? splits.folds.length ? `${integer(splits.folds.length)} grouped folds select models and thresholds using separate training and validation equipment.` : "No grouped folds are recorded. Model and threshold selection cannot be explained from these assignments."
        : "Reserved histories are for the separate final check after locking the recommendation. Opening this page does not score them."}</Explanation>
      {selected === "reserved" && <p className={styles.holdoutStatus}>{config?.holdout_status || "No reserved-history status is recorded."}</p>}
      {splits.development.length + splits.holdout.length === 0 && <p className={styles.inlineNote}>No equipment assignments are recorded.</p>}
    </>}
    <p className={styles.boundaryNote}>Recorded test evidence, not deployment approval.</p>
  </Panel>;
}

function Explanation({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return <div className={styles.explanation} aria-live="polite" aria-atomic="true"><motion.p key={String(children)} initial={reduced ? false : { opacity: .6 }} animate={{ opacity: 1 }} transition={{ duration: reduced ? 0 : .18 }}>{children}</motion.p></div>;
}
