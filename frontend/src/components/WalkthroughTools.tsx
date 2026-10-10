import { useMotionPreference } from "../hooks/useMotionPreference";
import { type ReactNode } from "react";
import { motion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";
import type { AcceptanceCriteria, CandidateVerdict } from "../api/types";
import { candidateLabel, integer } from "../format";
import { Badge } from "./Chrome";

export function WalkthroughChoice<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string; disabled?: boolean }[]; onChange: (value: T) => void;
}) {
  return <div className="walkthrough-choice" role="group" aria-label={label}>
    {options.map(option => <button key={option.value} type="button" aria-pressed={value === option.value}
      disabled={option.disabled} onClick={() => onChange(option.value)}>{option.label}</button>)}
  </div>;
}

export function WarningWindow({ criteria }: { criteria: AcceptanceCriteria }) {
  return <section className="walkthrough-window" aria-label="Useful warning window">
    <div className="walkthrough-window-heading"><h3>When a warning counts</h3></div>
    <div className="walkthrough-window-track" aria-hidden="true"><span /><span /><span /><i /></div>
    <div className="walkthrough-window-labels"><span>Earlier</span><span>In time</span><span>Late</span><span>Failure</span></div>
    <p className="walkthrough-window-range">{criteria.horizon_cycles} to {criteria.min_useful_lead} cycles before failure · Diagram, not a time scale</p>
  </section>;
}

export function GuidedModelRows({ models, emphasis }: { models: CandidateVerdict[]; emphasis: "warnings" | "tests" }) {
  const reduced = useMotionPreference();
  function bar(value: number, total: number, children: ReactNode) {
    const fraction = total > 0 ? Math.max(0, Math.min(1, value / total)) : 0;
    return <><strong>{children}</strong><span className="guided-model-bar" aria-hidden="true"><motion.span initial={false}
      animate={{ scaleX: fraction }} transition={reduced ? { duration: 0 } : { duration: motionTokens.duration.standard, ease: motionTokens.ease.enter }} /></span></>;
  }
  return <div className="guided-model-rows" data-testid="walkthrough-model-rows" data-emphasis={emphasis}>
    {models.map(model => <section className="guided-model-row" key={`${model.candidate}/${model.config_id}`} aria-label={candidateLabel(model.candidate, model.config_id)}>
      <div className="guided-model-name"><h3>{candidateLabel(model.candidate, model.config_id)}</h3><Badge tone={model.qualifies === true ? "ok" : model.qualifies === false ? "bad" : "neutral"}>{model.qualifies === true ? "Pass" : model.qualifies === false ? "Fail" : "Unavailable"}</Badge></div>
      <dl><div className="guided-warning-value"><dt>Healthy sensors</dt><dd>{bar(model.clean.detected, model.clean.engines, `${integer(model.clean.detected)} / ${integer(model.clean.engines)}`)}</dd></div>
        <div className="guided-warning-value"><dt>Weakest fault</dt><dd>{model.worst_metrics ? bar(model.worst_metrics.detected, model.worst_metrics.engines, `${integer(model.worst_metrics.detected)} / ${integer(model.worst_metrics.engines)}`) : "Unavailable"}</dd></div>
        <div className="guided-tests-value"><dt>Required tests</dt><dd>{model.required_scenarios > 0 ? bar(model.required_passed, model.required_scenarios, `${model.required_passed} / ${model.required_scenarios}`) : "Unavailable"}</dd></div></dl>
    </section>)}
  </div>;
}
