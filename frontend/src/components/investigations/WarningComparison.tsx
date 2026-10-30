import { percent } from "../../format";
import styles from "../../views/investigations.module.css";

export function WarningComparison({ before, after, label = "Useful warnings", beforeLabel = "Without sensor fault", afterLabel = "With sensor fault", lowerIsBetter = false }: {
  before: number | null | undefined; after: number | null | undefined; label?: string; beforeLabel?: string; afterLabel?: string; lowerIsBetter?: boolean;
}) {
  const difference = before == null || after == null ? null : (after - before) * 100;
  const improved = difference !== null && (lowerIsBetter ? difference < 0 : difference > 0);
  const change = difference === null ? "Comparison unavailable" : Math.abs(difference) < .05 ? "No change"
    : `${Math.abs(difference).toFixed(1).replace(/\.0$/, "")} percentage points ${difference < 0 ? "lower" : "higher"}`;
  return <figure className={styles.comparison}>
    <figcaption><span>{label}</span><strong className={difference && !improved ? styles.worse : improved ? styles.better : undefined}>{change}</strong></figcaption>
    {[{ name: beforeLabel, value: before, faulted: false }, { name: afterLabel, value: after, faulted: true }].map(row => <div className={styles.comparisonRow} key={row.name}>
      <span>{row.name}</span><div className={styles.comparisonTrack} aria-hidden="true"><span data-faulted={row.faulted && difference !== null && Math.abs(difference) >= .05 && !improved || undefined} data-improved={row.faulted && improved || undefined}
        style={{ width: row.value == null ? "0%" : `${Math.max(0, Math.min(1, row.value)) * 100}%` }} /></div><strong>{percent(row.value, lowerIsBetter ? 1 : 0)}</strong>
    </div>)}
  </figure>;
}
