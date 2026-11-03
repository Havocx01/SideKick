import { useEffect, useRef, useState } from "react";
import { ApiError, investigations } from "../../api/client";
import type { CleanMetrics, FindingCriterion, ThresholdCheck as Check, ThresholdPoint } from "../../api/types";
import { Button } from "../Chrome";
import { percent } from "../../format";
import { Disclosure } from "./Disclosure";
import { validExposure } from "./EquipmentAlarms";
import { WarningComparison } from "./WarningComparison";
import styles from "../../views/investigations.module.css";

export function CleanAlarmSummary({ clean }: { clean: CleanMetrics | undefined }) {
  const available = clean?.equipment?.filter(row => validExposure(row.exposure)).length;
  return <>
    {(clean?.meanEquipmentBurden !== undefined || clean?.worstEquipmentBurden !== undefined) && <dl className={styles.metrics}>
      <div><dt>Mean machine alarm burden</dt><dd>{percent(clean.meanEquipmentBurden, 1)}</dd></div>
      <div><dt>Worst machine alarm burden</dt><dd>{percent(clean.worstEquipmentBurden, 1)}</dd></div>
    </dl>}
    <p className={styles.footnote}>{available !== undefined && clean
      ? `Eligible alarm windows: ${available} of ${clean.histories} machines. ${Math.max(0, clean.histories - available)} unavailable. Missing windows are not zero alarms.`
      : "Machine alarm window coverage was not provided."}</p>
  </>;
}

function Point({ title, point }: { title: string; point: ThresholdPoint }) {
  return <div className={styles.stack}><strong>{title}: {point.threshold}</strong><dl className={styles.metrics}>
    <div><dt>Useful warnings</dt><dd>{percent(point.clean.detection)}</dd></div>
    <div><dt>Pooled early alarm burden</dt><dd>{percent(point.clean.alarmBurden, 1)}</dd></div>
    <div><dt>Machine histories</dt><dd>{point.clean.histories}</dd></div>
  </dl><CleanAlarmSummary clean={point.clean} /></div>;
}

const statusLabels = { qualified: "A threshold meets the development limits", no_qualifying_threshold: "No qualifying threshold in this check", insufficient_evidence: "Threshold evidence is incomplete" };

export function ThresholdCheck({ context, criterion, disabled }: { context: string; criterion: FindingCriterion; disabled?: boolean }) {
  const [result, setResult] = useState<Check | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The parent keys this check by setup, model, and scope; old responses must stay with the old selection.
  const request = useRef(0);
  useEffect(() => () => { request.current++; }, []);

  async function check() {
    const id = ++request.current;
    setBusy(true); setError(""); setResult(null);
    try {
      const checked = await investigations.checkThreshold(context, { criterion });
      if (request.current === id) setResult(checked);
    } catch (failure) {
      if (request.current === id) setError(failure instanceof ApiError ? failure.detail || failure.message : failure instanceof Error ? failure.message : "Threshold check failed.");
    } finally { if (request.current === id) setBusy(false); }
  }

  return <section className={styles.stack} aria-label="Warning threshold check">
    <div className={styles.actions}><Button type="button" variant="secondary" disabled={disabled || busy} loading={busy} onClick={check}>Check warning threshold</Button></div>
    <p className={styles.footnote}>Check the fixed 80% useful-warning requirement and 5% alarm budget on this setup's development histories. Workspace computation only; no AI request. This check does not apply a threshold, retrain a model, or validate on fresh data.</p>
    {busy && <p role="status" className={styles.footnote}>Checking recorded development scores…</p>}
    {error && <p role="alert" className={styles.error}>{error} Use Check warning threshold to retry.</p>}
    {result && <div className={styles.stack}>
      <p role="status"><strong>{statusLabels[result.status]}</strong></p>
      {result.reasons.length > 0 && <ul>{result.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      <Point title="Current threshold" point={result.current} />
      {result.suggested && <>
        <Point title="Suggested threshold (not applied)" point={result.suggested} />
        <div className={styles.comparisonGrid}>
          <WarningComparison label="Useful warnings" before={result.current.clean.detection} after={result.suggested.clean.detection} beforeLabel="Current threshold" afterLabel="Suggested threshold" />
          <WarningComparison label="Pooled early alarm burden" before={result.current.clean.alarmBurden} after={result.suggested.clean.alarmBurden} beforeLabel="Current threshold" afterLabel="Suggested threshold" lowerIsBetter />
        </div>
      </>}
      {!result.suggested && result.bestWithinAlarmCap && <Disclosure title="Best checked threshold within the alarm cap" description="This point did not satisfy every requirement.">
        <Point title="Checked threshold (not applied)" point={result.bestWithinAlarmCap} />
      </Disclosure>}
      <p className={styles.footnote}>{result.evaluatedThresholds} of {result.candidateThresholds} candidate thresholds evaluated. {result.note} Development evidence only; engineer review remains required.</p>
    </div>}
  </section>;
}
