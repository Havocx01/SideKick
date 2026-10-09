import { motion } from "motion/react";
import { integer } from "../format";
import { RollingNumber } from "./cult/RollingNumber";

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
  return <div>
    <div className="benchmark-bar-label"><span>{label}</span><strong>
      {detected !== undefined && histories !== undefined
        ? <><RollingNumber value={detected} format={integer} /> / <RollingNumber value={histories} format={integer} /></>
        : <RollingNumber value={fraction * 100} format={wholePercent} />}
    </strong></div>
    <div className={`benchmark-track${fault ? " fault" : ""}`} aria-hidden="true">
      <motion.span data-overview-fill initial={{ scaleX: 0 }} animate={{ scaleX: fill }}
        transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }} />
    </div>
  </div>;
}
