import { useEffect } from "react";
import { motion, useSpring, useTransform } from "motion/react";
import styles from "./rolling-number.module.css";
import { useMotionPreference } from "../../hooks/useMotionPreference";

// Adapted from Cult UI RollingNumber (MIT; see ./LICENSE).
// https://www.cult-ui.com/r/rolling-number.json
interface RollingNumberProps {
  value: number;
  precision?: number;
  format?: (value: number) => string;
  mass?: number;
  stiffness?: number;
  damping?: number;
}

const localeFormat = (value: number) => value.toLocaleString();

export function RollingNumber({
  value, precision = 0, format = localeFormat,
  mass = 0.8, stiffness = 150, damping = 24,
}: RollingNumberProps) {
  const valid = Number.isFinite(value);
  const reducedMotion = useMotionPreference();
  const target = valid ? value : 0;
  const spring = useSpring(0, { mass, stiffness, damping });
  const display = useTransform(spring, current => format(Number(current.toFixed(precision))));
  useEffect(() => { if (reducedMotion) spring.jump(target); else spring.set(target); }, [spring, target, reducedMotion]);
  const final = valid ? format(Number(value.toFixed(precision))) : "—";

  return <span className={styles.number} data-rolling-number data-value={final}>
    <span className={styles.measure} aria-hidden="true">{final}</span>
    {valid && reducedMotion ? <span className={styles.display} aria-hidden="true">{final}</span>
      : valid ? <motion.span className={styles.display} aria-hidden="true">{display}</motion.span>
      : <span className={styles.display} aria-hidden="true">—</span>}
    <span className="sr-only">{final}</span>
  </span>;
}
