import { useMotionPreference } from "../hooks/useMotionPreference";
import type { AlertMetrics, CandidateVerdict, AcceptanceCriteria } from "../api/types";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";
import { integer, percent, scenarioLabel, scenarioSummary } from "../format";

export function WarningCounts({ metrics, label, fault = false, compact = false, animated = false }: { metrics: AlertMetrics; label: string; fault?: boolean; compact?: boolean; animated?: boolean }) {
  const reduced = useMotionPreference();
  const outcomes = [
    { label: "In time", value: metrics.detected, tone: "in-time" },
    { label: "Late", value: metrics.late, tone: "late" },
    { label: "Missed", value: metrics.missed, tone: "missed" }
  ];
  return <section className="warning-counts" aria-label={label}>
    <h3>{label}</h3>
    <p className="warning-count"><strong>{integer(metrics.detected)} / {integer(metrics.engines)}</strong>{!compact && <span>equipment histories warned in time</span>}</p>
    <div className="outcome-bar" role="img" aria-label={`${label}: ${metrics.detected} in time, ${metrics.late} late, ${metrics.missed} missed, out of ${metrics.engines} histories`}>
      {(compact ? [{ label: "In time", value: metrics.detected, tone: "in-time" }, { label: "Not in time", value: metrics.late + metrics.missed, tone: "not-in-time" }] : outcomes).filter(item => animated || item.value > 0).map(item => {
        const width = `${metrics.engines > 0 ? item.value / metrics.engines * 100 : 0}%`;
        return animated ? <motion.span key={item.tone} className={item.tone} initial={false} animate={{ width }}
          transition={reduced ? { duration: 0 } : { duration: motionTokens.duration.standard, ease: motionTokens.ease.enter }} />
          : <span key={item.tone} className={item.tone} style={{ width }} />;
      })}
    </div>
    {!compact && <>
      <dl className="outcome-key">{outcomes.map(item => <div key={item.tone}><dt><i className={item.tone} aria-hidden="true" />{item.label}</dt><dd>{integer(item.value)}</dd></div>)}</dl>
      <div className="early-alarm"><span title="Share of eligible early cycles spent in alarm">Early alarm time{fault ? " · this fault" : ""}<span className="sr-only"> (share of eligible early cycles in alarm)</span></span><strong>{metrics.early_alarm_burden == null ? "Unavailable" : percent(metrics.early_alarm_burden, 2)}</strong></div>
    </>}
  </section>;
}

export function WarningBreakdown({ verdict }: { verdict: CandidateVerdict }) {
  const rows = [
    { label: "In time", value: (metrics: AlertMetrics) => integer(metrics.detected) },
    { label: "Late", value: (metrics: AlertMetrics) => integer(metrics.late) },
    { label: "Missed", value: (metrics: AlertMetrics) => integer(metrics.missed) },
    { label: "Early alarm time", value: (metrics: AlertMetrics) => metrics.early_alarm_burden == null ? "Unavailable" : percent(metrics.early_alarm_burden, 2) }
  ];
  return <div className="table-scroll">
    <table className="result-breakdown" aria-label="Warning breakdown">
      <thead><tr><th scope="col">Outcome</th><th scope="col" className="num">Healthy sensors</th><th scope="col" className="num">Lowest detection fault</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th><td className="num">{row.value(verdict.clean)}</td><td className="num">{verdict.worst_metrics ? row.value(verdict.worst_metrics) : "Unavailable"}</td></tr>)}</tbody>
    </table>
  </div>;
}

export function WarningDefinitions({ verdict, criteria }: { verdict: CandidateVerdict; criteria: AcceptanceCriteria }) {
  const fault = verdict.worst_metrics;
  return <details className="metric-definitions"><summary>How warnings are counted</summary>
    {fault && <p>Fault: {scenarioLabel(verdict.worst_scenario_id ?? "")}. Histories tested: {integer(fault.engines)} / {integer(verdict.clean.engines)}.</p>}
    <dl className="metric-definition-grid">
      <div><dt>In time</dt><dd>A warning is in time when it is active {criteria.min_useful_lead} to {criteria.horizon_cycles} cycles before documented failure. A cycle is a reading interval, not necessarily an hour or minute.</dd></div>
      <div><dt>Late or missed</dt><dd>“Too late”: no warning in the useful window, but one in the late window before failure. “Missed warning window”: no warning in either window. Earlier alerts may still have occurred in either case.</dd></div>
      <div><dt>Early alarm time</dt><dd>The share of eligible early operating cycles spent in alarm. It is not the probability that an individual warning is false.</dd></div>
    </dl>
  </details>;
}

export function ResultStory({ verdict, criteria, showFault = true, inspectFaultHref, compact = false }: { verdict: CandidateVerdict; criteria: AcceptanceCriteria; showFault?: boolean; inspectFaultHref?: string; compact?: boolean }) {
  const fault = showFault ? verdict.worst_metrics : null;
  const change = fault && fault.engines === verdict.clean.engines ? fault.detected - verdict.clean.detected : null;
  const faultMissesLimit = fault && (fault.detection_fraction < criteria.min_detection_fraction || (fault.early_alarm_burden != null && fault.early_alarm_burden > criteria.max_early_alarm_burden));
  const faultContext = fault && verdict.worst_scenario_id && <div className="weakest-fault"><span>Lowest detection: <strong>{scenarioSummary(verdict.worst_scenario_id)}</strong></span>{inspectFaultHref && <Link className="result-text-link" to={inspectFaultHref}>Inspect fault</Link>}</div>;
  return <div className={compact ? "result-overview" : undefined}>
    {compact ? <p className="result-measure">Equipment histories warned in time</p> : faultContext}
    <div className="warning-comparison">
      <WarningCounts metrics={verdict.clean} label="Healthy sensors" compact={compact} />
      {showFault && (fault ? <WarningCounts metrics={fault} label="Lowest detection" fault compact={compact} /> : <p className="state">No required sensor-fault result is available.</p>)}
    </div>
    {fault && <p className={`result-consequence ${change != null && change < 0 && faultMissesLimit ? "warning-loss" : ""}`}>{change == null ? "Different coverage. Counts are not directly comparable." : change < 0 ? <><strong>{integer(-change)}</strong> fewer timely {change === -1 ? "warning" : "warnings"}</> : change > 0 ? <><strong>{integer(change)}</strong> more timely {change === 1 ? "warning" : "warnings"}</> : "No change in timely warnings"}</p>}
    {compact && faultContext}
    {verdict.coverage_complete === false && <p className="qualification fails" role="status">Required-case coverage is incomplete.</p>}
    {!compact && <WarningDefinitions verdict={verdict} criteria={criteria} />}
  </div>;
}
