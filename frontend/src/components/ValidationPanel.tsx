import { useEffect, useState } from "react";
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
  const [params, setParams] = useSearchParams();
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
  async function cancelJob(id: string) {
    setBusy(true); setError("");
    try { await experiments.cancel(id); setRevision(n => n + 1); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not cancel this job."); }
    finally { setBusy(false); }
  }
  return <Panel title="Freeze and validate" description="Lock the recommended model, then check it once on histories kept out of model selection." aside={!location.pathname.endsWith("/pilot") && !exposed ? <Link to={`/experiments/${experimentId}/pilot`}>Agree an equipment pilot</Link> : undefined}>
    <p className="note">{recommendation ? `Model to freeze: ${candidateLabel(recommendation.candidate, recommendation.config_id)}. This is the recommendation, regardless of the model being inspected above.` : "No development recommendation is available to freeze."}</p><div className="validation-status">
      <span>Frozen model <Badge>{frozen?.record?.status ?? "not frozen"}</Badge></span>
      <span>Reserved validation <Badge>{validation?.record?.status ?? "not scored"}</Badge></span>
    </div>
    {error && <p className="state error" role="alert">{error}</p>}
    {frozen?.record?.error && <p className="state error" role="alert">{frozen.record.error}</p>}
    {validation?.record?.error && <p className="state error" role="alert">{validation.record.error}</p>}
    {running?.job ? <div role="status"><p>{running.job.stage}. {Math.floor(running.job.elapsed_seconds ?? 0)} seconds elapsed. {running.job.total_work != null ? `${running.job.completed_work}/${running.job.total_work} ${running.job.work_unit}.` : ""}</p><Button disabled={busy || running.job.status === "cancelling"} onClick={() => cancelJob(running.job!.experiment_id)}>Cancel job</Button></div> : frozen?.record?.status !== "completed" ? <><Button variant="primary" loading={busy} disabled={!qualifies || !frozen} onClick={() => launch("freeze")}>Freeze recommendation</Button><p className="note">{qualifies ? "Refits the recommendation on development histories and locks the model, threshold, protocol and source version." : "No candidate met the development criteria. There is no model to freeze."}</p></> : validation?.record?.status === "completed" ? <><p>Final validation is complete. The reserved histories are now exposed.</p><Button onClick={() => { const next = new URLSearchParams(params); next.set("partition", "holdout"); next.delete("candidate"); setParams(next); }}>Inspect final validation</Button></> : exposed ? <p className="note">Scoring started, so these histories are exposed. This attempt cannot be repeated. Use fresh equipment histories for another final evaluation.</p> : <>
      <label className="confirmation"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)} />I confirm the reserved histories were not used to choose models, thresholds or fault rules.</label>
      <Button variant="primary" loading={busy} disabled={!confirmed || !validation} onClick={() => launch("validation")}>Evaluate reserved equipment once</Button>
      <p className="note">Known exposed histories are blocked. Cancelled or interrupted scoring still exposes the histories. NASA and synthetic results do not establish field performance.</p>
    </>}
    {frozen?.record?.artifact_digest && <details className="decision-detail"><summary>Frozen model identifiers</summary><p className="mono">Model {frozen.record.candidate}<br />Artifact {frozen.record.artifact_digest}</p></details>}
  </Panel>;
}
