import { useEffect, useState } from "react";
import { Check, CircleAlert } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { api, ApiError, experiments, type OperationState } from "../api/client";
import type { CandidateVerdict, FrozenModelRecord, ValidationRecord } from "../api/types";
import { candidateLabel } from "../format";
import { useApi } from "../hooks/useApi";
import { Badge, Button, Panel } from "./Chrome";

const active = (status?: string) => status != null && ["queued", "running", "cancelling"].includes(status);

export function ValidationPanel({ experimentId, qualifies, recommendation, onCompleted }: { experimentId: string; qualifies: boolean; recommendation?: CandidateVerdict | null; onCompleted: () => void }) {
  const health = useApi(() => api.health(), []);
  const [frozen, setFrozen] = useState<OperationState<FrozenModelRecord> | null>(null);
  const [validation, setValidation] = useState<OperationState<ValidationRecord> | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [params] = useSearchParams();
  const location = useLocation();
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!health.data?.can_freeze) return;
    let alive = true;
    let previousStatus = "";
    async function refresh() {
      try {
        const [f, v] = await Promise.all([experiments.frozen(experimentId), experiments.validation(experimentId)]);
        if (!alive) return;
        setFrozen(f); setValidation(v);
        if (previousStatus !== "completed" && v.record?.status === "completed") onCompleted();
        previousStatus = v.record?.status ?? "";
      } catch (e) { if (alive) setError(e instanceof Error ? e.message : "Could not load validation status."); }
    }
    void refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [experimentId, health.data?.can_freeze, revision]);
  if (!health.data?.can_freeze) return null;
  const running = active(frozen?.record?.status) ? frozen : active(validation?.record?.status) ? validation : null;
  async function launch(kind: "freeze" | "validation") {
    setBusy(true); setError("");
    try {
      if (kind === "freeze") await experiments.freeze(experimentId);
      else await experiments.validate(experimentId);
      setRevision(n => n + 1);
    } catch (e) { setError(e instanceof ApiError ? e.detail || e.message : e instanceof Error ? e.message : "Could not start this job."); }
    finally { setBusy(false); }
  }
  const exposed = validation?.record?.exposure_started_at != null;
  const locked = frozen?.record?.status === "completed";
  const validated = validation?.record?.status === "completed";
  const freezeStatus = !frozen ? "Loading" : locked ? "Locked" : frozen.record?.status ?? "Not locked";
  const validationStatus = !validation ? "Loading" : validated ? "Complete" : exposed && !active(validation.record?.status) ? "Histories exposed" : validation.record?.status ?? "Not scored";
  const [frozenCandidate, frozenConfig] = frozen?.record?.candidate.split("/") ?? [];
  const modelLabel = frozenCandidate ? candidateLabel(frozenCandidate, frozenConfig) : recommendation ? candidateLabel(recommendation.candidate, recommendation.config_id) : null;
  const errors = [...new Set([error, frozen?.record?.error, validation?.record?.error].filter(Boolean))];
  const viewingFinal = location.pathname.endsWith("/comparison") && params.get("partition") === "holdout";
  async function cancelJob(id: string) {
    setBusy(true); setError("");
    try { await experiments.cancel(id); setRevision(n => n + 1); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not cancel this job."); }
    finally { setBusy(false); }
  }
  return <div className="validation-panel"><Panel title="Freeze and validate" description="A one-time check on histories kept out of model selection.">
    <div className="validation-overview">
      <div className="validation-model">
        <h3>{locked ? "Frozen model" : "Recommended model"}</h3>
        <p>{modelLabel ?? "No recommendation available"}</p>
        <span className="note">{locked ? "Locked for this final check." : !modelLabel ? "No candidate met the development criteria." : "Uses the recommendation, even when inspecting another model."}</span>
      </div>
      <ol className="validation-steps" aria-label="Validation steps">
        <li aria-current={!locked && qualifies ? "step" : undefined}>
          <div className="validation-step-heading"><span className="validation-step-number" aria-hidden="true">{locked ? <Check size={16} /> : "1"}</span><h3>Lock model</h3><Badge tone={locked ? "ok" : active(frozen?.record?.status) ? "info" : frozen?.record?.status === "failed" ? "bad" : "neutral"}>{freezeStatus}</Badge></div>
          <p>Refit on development histories; lock the model, threshold, protocol and source version.</p>
        </li>
        <li aria-current={locked && !validated && (!exposed || active(validation?.record?.status)) ? "step" : undefined}>
          <div className="validation-step-heading"><span className="validation-step-number" aria-hidden="true">{validated ? <Check size={16} /> : "2"}</span><h3>Validate reserved histories</h3><Badge tone={validated ? "ok" : active(validation?.record?.status) ? "info" : exposed ? "warn" : validation?.record?.status === "failed" ? "bad" : "neutral"}>{validationStatus}</Badge></div>
          <p>Score the locked model once on histories it has not used for model selection.</p>
        </li>
      </ol>
    </div>
    {errors.length > 0 && <div className="validation-error" role="alert">
      <CircleAlert size={18} aria-hidden="true" />
      <div><h3>Validation needs attention</h3>{errors.map(message => <p key={message}>{message}</p>)}</div>
      {error && <Button variant="secondary" size="sm" onClick={() => { setError(""); setRevision(n => n + 1); }}>Refresh validation status</Button>}
    </div>}
    <div className="validation-action">
      {running ? <div className="validation-running" role="status">
        <p>{running.job ? <>{running.job.stage}. {Math.floor(running.job.elapsed_seconds ?? 0)} seconds elapsed.{running.job.total_work != null ? ` ${running.job.completed_work ?? 0}/${running.job.total_work} ${running.job.work_unit ?? "completed"}.` : ""}</> : "Waiting for job status."}</p>
        {running.job && <Button disabled={busy || running.job.status === "cancelling"} onClick={() => cancelJob(running.job!.experiment_id)}>Cancel job</Button>}
      </div> : !locked ? <>
        <Button variant="primary" loading={busy} disabled={!qualifies || !recommendation || !frozen || !validation} onClick={() => launch("freeze")}>Freeze recommendation</Button>
      </> : validated ? <>
        <p className="note">Final validation complete. These histories have now been exposed.</p>
        {!viewingFinal && <Link className="button" to={`/experiments/${experimentId}/comparison?partition=holdout`}>Inspect final validation</Link>}
      </> : exposed ? <p className="note">These histories have been exposed and cannot be scored again. Use fresh equipment histories for another final evaluation.</p> : <>
        <label className="confirmation"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />I confirm the reserved histories were not used to choose models, thresholds or fault rules.</label>
        <Button variant="primary" loading={busy} disabled={!confirmed || !validation} onClick={() => launch("validation")}>Evaluate reserved equipment once</Button>
        <p className="note">Scoring exposes these histories, even if cancelled or interrupted. Previously exposed histories are blocked.</p>
      </>}
    </div>
    <div className="validation-footer">
      <p className="note">Test evidence, not deployment approval. NASA and synthetic results do not establish field performance.</p>
      {!location.pathname.endsWith("/pilot") && !exposed && <Link to={`/experiments/${experimentId}/pilot`}>Agree an equipment pilot</Link>}
    </div>
    {frozen?.record?.artifact_digest && <details className="decision-detail disclosure-plain validation-identifiers"><summary>Frozen model identifiers</summary><dl><div><dt>Model</dt><dd><code>{frozen.record.candidate}</code></dd></div><div><dt>Artifact</dt><dd><code>{frozen.record.artifact_digest}</code></dd></div></dl></details>}
  </Panel></div>;
}
