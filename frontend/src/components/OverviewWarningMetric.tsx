import { motion } from "motion/react";
import { integer } from "../format";
import { RollingNumber } from "./cult/RollingNumber";
import { useMotionPreference } from "../hooks/useMotionPreference";

const wholePercent = (value: number) => `${value}%`;

export function OverviewWarningMetric({
  label, detected, histories, fraction, fault = false,
}: {
  label: string;
  detected?: number;
  histories?: number;
  fraction: number;
  fault?: boolean;
}) {
  const fill = Number.isFinite(fraction) ? Math.max(0, Math.min(1, fraction)) : 0;
  const reducedMotion = useMotionPreference();
  return <div>
    <div className="benchmark-bar-label"><span>{label}</span><strong>
      {detected !== undefined && histories !== undefined
        ? <><RollingNumber value={detected} format={integer} /> / <RollingNumber value={histories} format={integer} /></>
        : <RollingNumber value={fraction * 100} format={wholePercent} />}
    </strong></div>
    <div className={`benchmark-track${fault ? " fault" : ""}`} aria-hidden="true">
      <motion.span data-overview-fill initial={reducedMotion ? false : { scaleX: 0 }} animate={{ scaleX: fill }}
        transition={{ duration: reducedMotion ? 0 : 0.85, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  </div>;
}
