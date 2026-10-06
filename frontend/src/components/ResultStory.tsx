import type { AlertMetrics, CandidateVerdict, AcceptanceCriteria } from "../api/types";
import { Link } from "react-router-dom";
import { integer, percent, scenarioLabel, scenarioSummary } from "../format";

export function WarningCounts({ metrics, label, fault = false }: { metrics: AlertMetrics; label: string; fault?: boolean }) {
  const outcomes = [
    { label: "In time", value: metrics.detected, tone: "in-time" },
    { label: "Late", value: metrics.late, tone: "late" },
    { label: "Missed", value: metrics.missed, tone: "missed" }
  ];
  return <section className="warning-counts" aria-label={label}>
    <h3>{label}</h3>
    <p className="warning-count"><strong>{integer(metrics.detected)} / {integer(metrics.engines)}</strong><span>equipment histories warned in time</span></p>
    <div className="outcome-bar" role="img" aria-label={`${label}: ${metrics.detected} in time, ${metrics.late} late, ${metrics.missed} missed, out of ${metrics.engines} histories`}>
      {outcomes.filter(item => item.value > 0).map(item => <span key={item.tone} className={item.tone} style={{ width: `${metrics.engines > 0 ? item.value / metrics.engines * 100 : 0}%` }} />)}
    </div>
    <dl className="outcome-key">{outcomes.map(item => <div key={item.tone}><dt><i className={item.tone} aria-hidden="true" />{item.label}</dt><dd>{integer(item.value)}</dd></div>)}</dl>
    <div className="early-alarm"><span title="Share of eligible early cycles spent in alarm">Early alarm time{fault ? " · this fault" : ""}<span className="sr-only"> (share of eligible early cycles in alarm)</span></span><strong>{metrics.early_alarm_burden == null ? "Unavailable" : percent(metrics.early_alarm_burden, 2)}</strong></div>
  </section>;
}

export function ResultStory({ verdict, criteria, showFault = true, inspectFaultHref }: { verdict: CandidateVerdict; criteria: AcceptanceCriteria; showFault?: boolean; inspectFaultHref?: string }) {
  const fault = showFault ? verdict.worst_metrics : null;
  const change = fault && fault.engines === verdict.clean.engines ? fault.detected - verdict.clean.detected : null;
  const faultMissesLimit = fault && (fault.detection_fraction < criteria.min_detection_fraction || (fault.early_alarm_burden != null && fault.early_alarm_burden > criteria.max_early_alarm_burden));
  return <>
    {fault && verdict.worst_scenario_id && <div className="weakest-fault"><span>Weakest fault: <strong>{scenarioSummary(verdict.worst_scenario_id)}</strong></span>{inspectFaultHref && <Link to={inspectFaultHref}>Inspect fault</Link>}</div>}
    <div className="warning-comparison">
      <WarningCounts metrics={verdict.clean} label="Healthy sensors" />
      {showFault && (fault ? <WarningCounts metrics={fault} label="Weakest sensor fault" fault /> : <p className="state">No required sensor-fault result is available.</p>)}
    </div>
    {fault && <p className={`result-consequence ${change != null && change < 0 && faultMissesLimit ? "warning-loss" : ""}`}>{change == null ? "Different coverage. Counts are not directly comparable." : change < 0 ? <><strong>{integer(-change)}</strong> fewer timely {change === -1 ? "warning" : "warnings"}</> : change > 0 ? <><strong>{integer(change)}</strong> more timely {change === 1 ? "warning" : "warnings"}</> : "No change in timely warnings"}</p>}
    {verdict.coverage_complete === false && <p className="qualification fails" role="status">Required-case coverage is incomplete.</p>}
    <details className="metric-definitions"><summary>What do these numbers mean?</summary>
      {fault && <p>Fault: {scenarioLabel(verdict.worst_scenario_id ?? "")}. Histories tested: {integer(fault.engines)} / {integer(verdict.clean.engines)}.</p>}
      <p>A warning is in time when it is active {criteria.min_useful_lead} to {criteria.horizon_cycles} operating cycles before the documented failure. A cycle is a reading interval, not necessarily an hour or minute.</p>
      <p>“Too late” means no warning was active in the useful window, but one was active in the late window before failure. “Missed warning window” means neither a useful nor a late warning was recorded. Earlier alerts may still have occurred in either case.</p>
      <p>Time spent warning too early is the share of eligible early operating cycles spent in alarm. It is not the probability that an individual warning is false.</p>
    </details>
  </>;
}

export function qualificationReason(verdict: CandidateVerdict) {
  if (verdict.coverage_complete === false) return "Required fault cases did not cover all expected histories.";
  if (verdict.clean.early_alarm_burden == null) return "Early-alarm time is unavailable on healthy readings.";
  if (!verdict.passes_clean) return "Healthy readings missed a test limit.";
  if (!verdict.passes_all_required) return "Some fault cases missed a limit or could not be assessed.";
  return `It met the warning and early-alarm limits in all ${verdict.required_scenarios} required fault cases.`;
}
