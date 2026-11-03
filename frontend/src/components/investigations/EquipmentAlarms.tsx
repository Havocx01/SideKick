import type { AlarmExposure, EquipmentAlarmEvidence } from "../../api/types";
import { percent } from "../../format";
import { Disclosure } from "./Disclosure";
import { WarningComparison } from "./WarningComparison";
import styles from "../../views/investigations.module.css";

export function validExposure(value: AlarmExposure | null): boolean {
  return value !== null && [value.eligible_cycles, value.alarm_eligible_cycles, value.scored_cycles].every(Number.isSafeInteger)
    && value.eligible_cycles > 0 && value.alarm_eligible_cycles >= 0 && value.alarm_eligible_cycles <= value.eligible_cycles
    && value.scored_cycles >= value.eligible_cycles;
}

function summary(values: AlarmExposure[]) {
  if (!values.length) return { pooled: null, mean: null, worst: null };
  const burdens = values.map(value => value.alarm_eligible_cycles / value.eligible_cycles);
  return {
    pooled: values.reduce((total, value) => total + value.alarm_eligible_cycles, 0) / values.reduce((total, value) => total + value.eligible_cycles, 0),
    mean: burdens.reduce((total, value) => total + value, 0) / burdens.length,
    worst: Math.max(...burdens)
  };
}

function Exposure({ value }: { value: AlarmExposure | null }) {
  if (value === null) return <>Unavailable: window not recorded</>;
  if (value.eligible_cycles === 0 && value.alarm_eligible_cycles === 0 && Number.isSafeInteger(value.scored_cycles) && value.scored_cycles >= 0) {
    return <>Unavailable: no eligible window<div className={styles.reason}>0 / 0 alarm / eligible cycles</div><div className={styles.reason}>{value.scored_cycles} scored cycles</div></>;
  }
  if (!validExposure(value)) return <>Unavailable: invalid recorded counts</>;
  return <>{percent(value.alarm_eligible_cycles / value.eligible_cycles, 1)}<div className={styles.reason}>{value.alarm_eligible_cycles} / {value.eligible_cycles} alarm / eligible cycles</div>
    <div className={styles.reason}>{value.scored_cycles} scored cycles</div></>;
}

const warningLabels = { detected: "In time", late: "Late", missed: "Missed" };

export function EquipmentAlarms({ evidence }: { evidence?: EquipmentAlarmEvidence[] }) {
  const matched = (evidence ?? []).filter(row => validExposure(row.clean) && validExposure(row.faulted));
  const clean = summary(matched.map(row => row.clean!));
  const faulted = summary(matched.map(row => row.faulted!));
  return <Disclosure title="Machine alarm evidence" description={evidence?.length ? "Pooled, mean, and worst alarm burden, with individual warning outcomes and recorded cycle counts." : "Per-machine alarm counts were not recorded for this result."}>
    {!evidence?.length ? <p className={styles.footnote}>Machine alarm burden is unavailable. Historical totals and changed-history lists cannot recover individual alarm windows; no counts are inferred.</p> : <div className={styles.stack}>
      <p className={styles.footnote}>Summaries use the same {matched.length} of {evidence.length} machines with valid eligible windows on both sides. {matched.length < evidence.length && "Machines with unavailable windows are excluded from all three summaries, not treated as zero. "}These summaries describe recorded development evidence, not operational validation.</p>
      <div className={styles.equipmentComparisons}>
        <WarningComparison label="Pooled alarm burden" before={clean.pooled} after={faulted.pooled} lowerIsBetter />
        <WarningComparison label="Mean machine alarm burden" before={clean.mean} after={faulted.mean} lowerIsBetter />
        <WarningComparison label="Worst machine alarm burden" before={clean.worst} after={faulted.worst} lowerIsBetter />
      </div>
      <p className={styles.footnote}>Pooled burden divides total alarm cycles by total eligible cycles. Mean weights each machine equally; worst is the highest machine burden on each side and may come from different machines. A subset summary can differ from the overall result above.</p>
      <div className="table-scroll" role="region" aria-label="Machine alarm evidence table" tabIndex={0}><table className={styles.equipmentTable} aria-label="Machine alarm counts"><thead><tr>
        <th>Machine</th><th>Without fault: warning</th><th>Without fault: alarm burden</th><th>With fault: warning</th><th>With fault: alarm burden</th>
      </tr></thead><tbody>{evidence.map(row => <tr key={row.equipment_id}>
        <th scope="row">{row.equipment_id}</th><td>{warningLabels[row.clean_warning]}</td><td><Exposure value={row.clean} /></td>
        <td>{warningLabels[row.faulted_warning]}</td><td><Exposure value={row.faulted} /></td>
      </tr>)}</tbody></table></div>
      <p className={styles.footnote}>Alarm burden counts early alarm cycles within the eligible window. An unavailable window does not mean no alarms. Useful warnings and early alarms measure different outcomes.</p>
    </div>}
  </Disclosure>;
}
