import { useEffect, useState } from "react";
import { Check, Circle, Database, LoaderCircle } from "lucide-react";
import { investigations } from "../../api/client";
import type { ContextPreparation, ContextPreparationState } from "../../api/types";
import { Badge, Button, Callout, Panel } from "../Chrome";
import { useApi } from "../../hooks/useApi";
import { Disclosure } from "./Disclosure";
import styles from "../../views/investigations.module.css";

const stages = ["Generate sample", "Fit models", "Check baseline"];
const stageIndex: Record<ContextPreparation["stage"], number> = { queued: 0, generating: 0, training: 1, calibrating: 2, checking: 2, ready: 3 };

export function ContextSetup({ ready, onReady }: { ready: boolean; onReady: () => void }) {
  const state = useApi(() => investigations.preparation(), []);
  const [last, setLast] = useState<ContextPreparationState | null>(null);
  const [submitted, setSubmitted] = useState<ContextPreparation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = state.data ?? last;
  const job = data?.job ?? submitted;
  const running = job?.status === "queued" || job?.status === "running" || job?.status === "cancelling";
  const { reload } = state;
  useEffect(() => { if (state.data) setLast(state.data); }, [state.data]);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(reload, 1000);
    return () => clearInterval(timer);
  }, [running, reload]);
  useEffect(() => { if (job?.status === "completed") onReady(); }, [job?.id, job?.status, onReady]);

  async function prepare() {
    setBusy(true); setError("");
    try {
      const result = await investigations.prepareContext(crypto.randomUUID().replace(/-/g, ""));
      setSubmitted(result); setLast({ job: result, outdated: data?.outdated ?? 0 }); reload();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Preparation could not start. Try again."); }
    finally { setBusy(false); }
  }

  async function cancel() {
    if (!job) return;
    setBusy(true); setError("");
    try {
      const result = await investigations.cancelPreparation(job.id);
      setSubmitted(result); setLast({ job: result, outdated: data?.outdated ?? 0 }); reload();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Cancellation could not be saved. Try again."); }
    finally { setBusy(false); }
  }

  const content = <div className={styles.stack}>
    <p>Train models on a rotating-machine sample, then hold the models and warning thresholds fixed while you test sensor faults.</p>
    <div className={styles.sampleFacts}><span><Database size={16} aria-hidden="true" />26 simulated machine histories</span><span>22 for development</span><span>4 reserved and left untouched</span></div>
    <p className={styles.footnote}>Synthetic practice data, not your uploaded equipment data or field validation. Preparation runs locally and makes no AI requests.</p>
    {!!data?.outdated && <Callout tone="warn" title="Older model setups need refreshing">{data.outdated} older {data.outdated === 1 ? "setup no longer matches" : "setups no longer match"} this version of Sidekick. Your previous investigations and files are kept.</Callout>}
    {job && <div className={styles.preparationState} role="status" aria-live="polite">
      <div className={styles.heading}><strong>{job.status === "cancelling" ? "Stopping preparation" : running ? "Preparing your sample models" : job.status === "completed" ? "Sample models ready" : "Preparation stopped"}</strong>
        <Badge tone={running ? "info" : job.status === "completed" ? "ok" : "warn"}>{job.status === "cancelling" ? "Stopping" : running ? "In progress" : job.status === "completed" ? "Ready" : job.status}</Badge></div>
      {(running || job.status === "completed") && <ol className={styles.steps} aria-label="Model preparation progress">
        {stages.map((label, index) => <li key={label} data-current={stageIndex[job.stage] === index && running || undefined} data-complete={stageIndex[job.stage] > index || undefined}>
          {stageIndex[job.stage] > index ? <Check size={16} aria-hidden="true" /> : stageIndex[job.stage] === index && running ? <LoaderCircle className={styles.spinner} size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />}<span>{label}</span>
        </li>)}
      </ol>}
      {running && <p className={styles.footnote}>You can leave this page and come back. Sidekick keeps the preparation status.</p>}
      {job.error && <p>{job.error}</p>}
    </div>}
    {(error || state.error) && <div role="alert" className={styles.error}><p>{error || "Could not refresh preparation status. Your previous results remain available."}</p>
      {state.error && <Button variant="ghost" onClick={reload}>Refresh preparation status</Button>}</div>}
    <div className={styles.actions}>
      {running ? <Button variant="secondary" disabled={busy || job?.status === "cancelling"} onClick={cancel}>{job?.status === "cancelling" ? "Stopping preparation" : "Cancel preparation"}</Button>
        : <Button variant={ready ? "secondary" : "primary"} loading={busy} onClick={prepare}>{job && job.status !== "completed" ? "Try preparation again" : ready ? "Prepare another sample" : "Prepare sample models"}</Button>}
    </div>
  </div>;

  return ready && !running ? <div className={styles.readySetup}><p role="status"><Check size={16} aria-hidden="true" /><strong>Model setup ready.</strong> Choose your concern below to start an investigation.</p>
    <Disclosure title="Prepare another model setup" description="Create a fresh synthetic sample without changing saved investigations.">{content}</Disclosure></div>
    : <Panel title="Prepare models for investigation" description="Start with a sample. No terminal commands or API key needed.">{content}</Panel>;
}
