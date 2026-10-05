import type { AlertMetrics, CandidateVerdict, AcceptanceCriteria } from "../api/types";
import { integer, percent, scenarioLabel } from "../format";

export function WarningCounts({ metrics, label }: { metrics: AlertMetrics; label: string }) {
  return <section className="warning-counts" aria-label={label}>
    <h3>{label}</h3>
    <p className="warning-count"><strong>{integer(metrics.detected)} / {integer(metrics.engines)}</strong> <span>histories warned in time</span></p>
    <dl className="warning-breakdown">
      <div><dt>Warnings too late</dt><dd>{integer(metrics.late)}</dd></div>
      <div><dt>Missed warning window</dt><dd>{integer(metrics.missed)}</dd></div>
      <div><dt>Time spent warning too early</dt><dd>{metrics.early_alarm_burden == null ? "Unavailable" : percent(metrics.early_alarm_burden, 2)}</dd></div>
    </dl>
  </section>;
}

export function ResultStory({ verdict, criteria, showFault = true }: { verdict: CandidateVerdict; criteria: AcceptanceCriteria; showFault?: boolean }) {
  const fault = showFault ? verdict.worst_metrics : null;
  const change = fault && fault.engines === verdict.clean.engines ? fault.detected - verdict.clean.detected : null;
  return <>
    <div className="warning-comparison">
      <WarningCounts metrics={verdict.clean} label="Healthy sensors" />
      {showFault && (fault ? <WarningCounts metrics={fault} label="Weakest required sensor fault" /> : <p className="state">No required sensor-fault result is available.</p>)}
    </div>
    {fault && <p className="result-consequence">{change == null ? "Different numbers of histories were evaluated. Compare coverage before interpreting the change." : change < 0 ? `${integer(-change)} fewer histories received a warning in time with this fault.` : change > 0 ? `${integer(change)} more histories received a warning in time with this fault.` : "The number of histories warned in time stayed the same with this fault."}</p>}
    {fault && <p className="note">Fault tested: {scenarioLabel(verdict.worst_scenario_id ?? "")}. Histories tested: {integer(fault.engines)} / {integer(verdict.clean.engines)}{verdict.coverage_complete === false ? ". Required-case coverage is incomplete." : "."}</p>}
    <details className="metric-definitions"><summary>What do these numbers mean?</summary>
      <p>A warning is in time when it is active {criteria.min_useful_lead} to {criteria.horizon_cycles} operating cycles before the documented failure. A cycle is a reading interval, not necessarily an hour or minute.</p>
      <p>“Too late” means no warning was active in the useful window, but one was active in the late window before failure. “Missed warning window” means neither a useful nor a late warning was recorded. Earlier alerts may still have occurred in either case.</p>
      <p>Time spent warning too early is the share of eligible early operating cycles spent in alarm. It is not the probability that an individual warning is false.</p>
    </details>
  </>;
}

export function qualificationReason(verdict: CandidateVerdict) {
  if (verdict.coverage_complete === false) return "Required fault cases did not cover all expected histories.";
  if (verdict.clean.early_alarm_burden == null) return "Time spent warning too early could not be measured with healthy sensors, so the model cannot qualify.";
  if (!verdict.passes_clean) return "It did not meet the warning or early-alarm limits with healthy sensors.";
  if (!verdict.passes_all_required) return `It passed ${verdict.required_passed} of ${verdict.required_scenarios} required fault cases. At least one case missed a limit or could not be assessed.`;
  return `It met the warning and early-alarm limits in all ${verdict.required_scenarios} required fault cases.`;
}
