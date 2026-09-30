import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, experiments } from "../api/client";
import type { ColumnMapping, DatasetRegistration, ExperimentRecord } from "../api/types";
import { Badge, Button, Field, Panel, Select, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { ArrowRight, Check, FlaskConical, Layers, Upload } from "lucide-react";
import { NumberField } from "@/registry/components/number-field/number-field";
import { integer, percent, scenarioLabel } from "../format";

export const activeJob = (status: string) => ["queued", "running", "cancelling"].includes(status);
function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.detail || error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Try again.";
}
const duration = (seconds: number) => `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;

function TrainingOnly({ children, upload = false }: { children: ReactNode; upload?: boolean }) {
  const health = useApi(() => api.health(), []);
  return (
    <StateBlock loading={health.loading} error={health.error}>
      {(upload ? health.data?.can_upload : health.data?.can_train) ? (
        children
      ) : (
        <Panel title="Training runs on your computer">
          <p>
            {health.data?.mode === "demo"
              ? "CSV uploads are local only. Try a synthetic sample here or run the app on your computer."
              : "This deployment displays recorded results. Upload and training are disabled here."}
          </p>
          {health.data?.can_train && (
            <p>
              <Link to="/new?source=sample">Run a sample experiment</Link>
            </p>
          )}
          <Link to="/comparison">Explore the recorded benchmark</Link>
        </Panel>
      )}
    </StateBlock>
  );
}

export function Start() {
  const health = useApi(() => api.health(), []);
  const selection = useApi(() => api.selection(), []);
  const example = selection.data?.ranked.find(row => row.candidate === "logistic_regression" && row.config_id === "lr2");
  return (
    <>
      <section className="welcome" aria-labelledby="welcome-heading">
        <div>
          <h1 id="welcome-heading">Test failure warnings before trusting them</h1>
          <p>Train on equipment histories. Test missing, frozen and drifting sensors. See which warnings hold up.</p>
          <div className="hero-actions">
            {health.data?.can_train ? (
              <Link className="button primary" to="/new?source=sample">Run sample experiment <ArrowRight size={16} aria-hidden="true" /></Link>
            ) : (
              <Link className="button primary" to="/comparison">Explore benchmark <ArrowRight size={16} aria-hidden="true" /></Link>
            )}
          </div>
          <p className="hero-footnote">{health.data?.can_train ? "Synthetic data · Local training · No API key" : "Recorded NASA results. No training required."}</p>
        </div>
        <div className="benchmark-preview">
          <div className="preview-heading"><h2>A clean score is only the start</h2><Badge>Recorded NASA</Badge></div>
          <div className="preview-subtitle">Logistic regression lr2 · Development evaluation</div>
          <StateBlock loading={selection.loading} error={selection.error}>
            {example ? (
              <>
                <div className="benchmark-bars">
                  <div>
                    <div className="benchmark-bar-label"><span>Original readings</span><strong>{integer(example.clean.detected)} / {integer(example.clean.engines)}</strong></div>
                    <div className="benchmark-track" aria-hidden="true"><span style={{ width: percent(example.clean.detection_fraction) }} /></div>
                  </div>
                  <div>
                    <div className="benchmark-bar-label"><span>Weakest required fault</span><strong>{example.worst_metrics ? `${integer(example.worst_metrics.detected)} / ${integer(example.worst_metrics.engines)}` : percent(example.worst_detection_required)}</strong></div>
                    <div className="benchmark-track fault" aria-hidden="true"><span style={{ width: percent(example.worst_detection_required) }} /></div>
                  </div>
                </div>
                <div className="preview-explanation">
                  <p>{scenarioLabel(example.worst_scenario_id ?? "")}. Counts show histories warned 10 to 30 cycles before failure. ABB field performance is unverified.</p>
                  <Link to="/comparison?candidate=logistic_regression%2Flr2">Inspect the evidence <ArrowRight size={16} aria-hidden="true" /></Link>
                </div>
              </>
            ) : <p className="note">Open the recorded comparison to inspect the available candidates and fault tests.</p>}
          </StateBlock>
        </div>
      </section>
      <section className="start-section" aria-labelledby="start-heading">
        <h2 id="start-heading">Choose where to start</h2>
        <StateBlock loading={health.loading} error={health.error}>
          <div className="start-actions">
            <section>
              <div className="start-option"><Layers size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Explore the recorded benchmark</h3><p>Compare models and replay sensor faults on NASA data.</p></div></div>
              <Link className="button" to="/comparison">Explore benchmark <ArrowRight size={16} aria-hidden="true" /></Link>
            </section>
            <section>
              <div className="start-option"><FlaskConical size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Run a synthetic experiment</h3><p>Generate {health.data?.sample_equipment ?? 60} simulated histories and test the models.</p></div></div>
              {health.data?.can_train ? <Link className="button" to="/new?source=sample">Set up sample <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
            <section>
              <div className="start-option"><Upload size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Use your equipment histories</h3><p>CSV up to 10 MB · Complete run-to-failure histories</p></div></div>
              {health.data?.can_upload ? <Link className="button" to="/new?source=upload">Upload CSV <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
          </div>
        </StateBlock>
      </section>
      <ol className="workflow" aria-label="Experiment workflow">
        {["Choose data", "Check histories", "Train and challenge", "Inspect results", "Export evidence"].map(step => <li key={step}><Check size={16} aria-hidden="true" />{step}</li>)}
      </ol>
      {health.data?.mode === "demo" && <p className="scope-note">The hosted sample uses 30 short histories, three sensors and four configurations. Two runs per browser per hour, one active server run, and shared daily limits apply. Results expire after 24 hours; restarts or idle shutdowns may clear them sooner. Export evidence to keep it.</p>}
      <p className="scope-note">Development evidence only. ABB field performance remains unverified.</p>
    </>
  );
}

export function NewExperiment() {
  const [params] = useSearchParams();
  return (
    <TrainingOnly upload={params.get("source") !== "sample"}>
      <ExperimentSetup />
    </TrainingOnly>
  );
}

function ExperimentSetup() {
  const health = useApi(() => api.health(), []);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [data, setData] = useState<DatasetRegistration | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [detection, setDetection] = useState(70);
  const [csvText, setCsvText] = useState("");
  const [burden, setBurden] = useState(10);
  const datasetId = params.get("dataset");
  const isSample = params.get("source") === "sample";
  function receive(value: DatasetRegistration) {
    setData(value);
    setComplete(value.complete_histories ?? false);
    setMapping(value.mapping ?? { equipment_id: "", cycle_index: "", sensors: [], failure_cycle: null });
  }
  useEffect(() => {
    if (!datasetId) {
      setData(null);
      setMapping(null);
      setError("");
      return;
    }
    let alive = true;
    setBusy(true);
    async function load(id: string) {
      try {
        const dataset = await experiments.dataset(id);
        if (alive) receive(dataset);
      } catch (error) {
        if (alive) setError(errorMessage(error));
      } finally {
        if (alive) setBusy(false);
      }
    }
    void load(datasetId);
    return () => {
      alive = false;
    };
  }, [datasetId]);
  async function prepare(file?: File) {
    if (file && file.size > 10 * 1024 * 1024) {
      setError("CSV files must be 10 MB or smaller.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const value = file ? await experiments.upload(file) : await experiments.sample();
      receive(value);
      setParams({ source: file ? "upload" : "sample", dataset: value.dataset_id }, { replace: true });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!data || !mapping) return;
    setBusy(true);
    setError("");
    try {
      const assigned = [mapping.equipment_id, mapping.cycle_index, mapping.failure_cycle, ...mapping.sensors];
      const confirmed = { ...mapping, ignored: data.columns.filter(column => !assigned.includes(column)) };
      receive(await experiments.confirm(data.dataset_id, { mapping: confirmed, complete_histories: complete }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function start() {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const result = await experiments.create({
        dataset_id: data.dataset_id,
        min_detection_fraction: detection / 100,
        max_early_alarm_burden: burden / 100
      });
      navigate(`/experiments/${result.experiment_id}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  const role = (key: "equipment_id" | "cycle_index" | "failure_cycle", label: string) => (
    <Select
      label={label}
      disabled={busy}
      value={mapping?.[key] ?? (key === "failure_cycle" ? "__none" : "")}
      placeholder="Choose a column"
      onValueChange={value => setMapping(m => m && { ...m, [key]: value === "__none" ? null : value })}
      options={[...(key === "failure_cycle" ? [{ value: "__none", label: "No failure-cycle column" }] : []), ...(data?.columns ?? []).map(value => ({ value, label: value }))]}
    />
  );
  return (
    <>
      <header className="page-head">
        <h1>{isSample ? "Run a sample experiment" : "Use your equipment histories"}</h1>
        <p>Confirm the data and set your acceptance limits.</p>
      </header>
      <ol className="setup-steps" aria-label="Data setup steps">
        {["Choose data", "Confirm mapping", "Train models"].map((step, index) => <li key={step} aria-current={index === (!data ? 0 : data.confirmed ? 2 : 1) ? "step" : undefined}><span className="step-number">{index + 1}</span>{step}</li>)}
      </ol>
      {error && (
        <div className="state error" role="alert">
          {error} <Link to="/experiments">View your experiments</Link>
          {" · "}
          <Link to="/comparison">Explore recorded benchmark</Link>
        </div>
      )}
      {busy && <p role="status">Preparing your request. Please wait…</p>}
      {!data && (
        <Panel title={isSample ? "Generate a practice dataset" : "Choose a CSV"}>
          {isSample ? (
            <>
              <p>
                The sample contains {health.data?.sample_equipment ?? 60} simulated equipment histories. Its results
                demonstrate the workflow and do not validate performance on real machinery.{" "}
                {health.data?.mode === "demo" &&
                  "This compact hosted sample evaluates ten histories over five folds, using three sensors and one configuration per model family. Twenty histories remain unscored."}
              </p>
              <Button variant="primary" loading={busy} onClick={() => prepare()}>
                Generate sample data
              </Button>
            </>
          ) : (
            <>
              <p>
                Include at least 25 complete equipment histories: 20 are reserved, and the rest form five development
                folds. More histories give more useful comparisons.
              </p>
              <Field label="CSV file (up to 10 MB)">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  disabled={busy}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void prepare(file);
                  }}
                />
              </Field>
              <p className="note">
                Use UTF-8 CSV with unique headers. This version supports operating cycles and complete histories, not
                hours-based targets or machines that have not failed.
              </p>
              <details className="csv-paste">
                <summary>File picker not opening? Paste CSV instead</summary>
                <p className="note">Paste CSV with its header, or use Chrome or Edge to choose a file.</p>
                <Field label="CSV contents">
                  <textarea value={csvText} disabled={busy} onChange={event => setCsvText(event.target.value)} rows={8} placeholder={"equipment_id,cycle,sensor_1,failure_cycle\nengine_1,1,0.52,120"} />
                </Field>
                <Button disabled={busy || !csvText.trim()} loading={busy} onClick={() => prepare(new File([csvText], "pasted-histories.csv", { type: "text/csv" }))}>Use pasted CSV</Button>
              </details>
            </>
          )}
        </Panel>
      )}
      {data && (
        <>
          <Panel
            title={data.name}
            aside={
              <Badge tone={data.source === "synthetic" ? "warn" : "info"}>
                {data.source === "synthetic" ? "Synthetic demonstration" : "Uploaded data"}
              </Badge>
            }
          >
            <p>
              {data.row_count.toLocaleString()} readings across {data.columns.length} columns.
            </p>
            <details open={!data.confirmed}>
              <summary>Preview the first {data.preview.length} rows</summary>
              <p className="note">Sensor values are rounded for readability. Hover over a value to see its full precision. Training uses the original values.</p>
              <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {data.columns.map((c) => (<th key={c}>{c}</th>))}
                  </tr>
                </thead>
                <tbody>
                  {data.preview.map((row, i) => (
                    <tr key={i}>
                      {data.columns.map((c) => (<td key={c} title={String(row[c] ?? "missing")}>{row[c] === null ? "missing" : typeof row[c] === "number" ? row[c].toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(row[c])}</td>))}
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </details>
          </Panel>
          {!data.confirmed && mapping && (
            <Panel
              title="Confirm what each column means"
              description="Check suggested roles. Keep identifiers and failure targets out of sensor inputs."
            >
              <div className="mapping-roles">
                {role("equipment_id", "Equipment ID")}
                {role("cycle_index", "Cycle index")}
                {role("failure_cycle", "Known failure cycle")}
              </div>
              <fieldset disabled={busy}>
                <legend>Sensor columns</legend>
                <div className="sensor-options">
                  {data.columns.map((c) => (
                    <label key={c}>
                      <input
                        type="checkbox"
                        checked={mapping.sensors.includes(c)}
                        onChange={(e) =>
                          setMapping({
                            ...mapping,
                            sensors: e.target.checked ? [...mapping.sensors, c] : mapping.sensors.filter((s) => s !== c)
                          })
                        }
                      />
                      {c}
                    </label>
                  ))}
                </div>
              </fieldset>
              {!mapping.failure_cycle && (
                <label className="confirmation">
                  <input
                    type="checkbox"
                    checked={complete}
                    disabled={busy}
                    onChange={(e) => setComplete(e.target.checked)}
                  />
                  I confirm every equipment history ends at an observed failure. The final cycle is the failure cycle.
                </label>
              )}
              <p className="note">
                If a machine had not failed at its final reading, its history is censored and cannot be evaluated by
                this version.
              </p>
              <Button variant="primary" loading={busy}
                disabled={
                  !mapping.equipment_id || !mapping.cycle_index || !mapping.sensors.length ||
                  (!mapping.failure_cycle && !complete)
                }
                onClick={confirm}
              >
                Validate and confirm mapping
              </Button>
            </Panel>
          )}
          {data.confirmed && data.profile && data.splits && (
            <>
              <Panel title="Data checked: review the equipment split">
                <p>
                  <strong>{data.splits.development.length} development histories</strong> are divided into{" "}
                  {data.splits.folds.length} folds. Each machine is evaluated by models that did not train on it.{" "}
                  <strong>{data.splits.holdout.length} histories are reserved and will not be scored.</strong>
                </p>
                <details>
                  <summary>Inspect equipment assignments</summary>
                  <p>Reserved: {data.splits.holdout.join(", ")}</p>
                  {data.splits.folds.map((fold, i) => (
                    <p key={i}>
                      Validation fold {i + 1}: {fold.join(", ")}
                    </p>
                  ))}
                </details>
                <details>
                  <summary>Data findings ({data.profile.findings?.length ?? 0}) and confirmed mapping</summary>
                  <p>
                    Equipment: {data.mapping?.equipment_id}. Cycle: {data.mapping?.cycle_index}. Failure:{" "}
                    {data.mapping?.failure_cycle ?? "confirmed final reading"}. Sensors:{" "}
                    {data.mapping?.sensors.join(", ")}.
                  </p>
                  <ul>
                    {data.profile.findings?.map((f) => (<li key={f.code}>{f.message}</li>))}
                  </ul>
                </details>
                <p className="note">
                  Dataset fingerprint: <code>{data.profile.data_hash}</code>.{" "}
                  {health.data?.mode === "demo"
                    ? "The hosted sample has a fixed mapping. Use the local app for your own data."
                    : "This confirmed copy is fixed; upload another copy to change its mapping."}
                </p>
              </Panel>
              <Panel
                title="Choose the acceptance limits"
                description="70% detection and 10% early-alarm burden are demonstration settings, not operational recommendations."
              >
                <div className="mapping-roles">
                  <NumberField label="Minimum useful detection" value={detection} onValueChange={setDetection} min={0} max={100} suffix="%" disabled={busy} limitHint={false} />
                  <NumberField label="Maximum early-alarm burden" value={burden} onValueChange={setBurden} min={0} max={100} suffix="%" disabled={busy} limitHint={false} />
                </div>
                <p>
                  Detection counts machines warned 10 to 30 cycles before failure. Early-alarm burden measures how much
                  eligible healthy operating time is spent in an alert, more than 45 cycles before failure.
                </p>
                <p className="note">
                  Fixed for this version: five equipment folds, {health.data?.sample_configurations ?? 10} candidate
                  configurations, a 20-cycle feature window, and the required dropout, stuck-sensor and drift tests. No
                  holdout scoring or automatic deployment.
                </p>
                <Button variant="primary" loading={busy}
                  disabled={
                    !Number.isFinite(detection) || !Number.isFinite(burden) || detection < 0 || detection > 100 ||
                    burden < 0 ||
                    burden > 100
                  }
                  onClick={start}
                >
                  Train and challenge models
                </Button>
                <p className="note">
                  One experiment at a time. Runs stop after 15 minutes. You can leave this page and return through
                  Experiments.
                </p>
              </Panel>
            </>
          )}
        </>
      )}
    </>
  );
}

export function ExperimentHistory() {
  return (
    <TrainingOnly>
      <History />
    </TrainingOnly>
  );
}
function History() {
  const health = useApi(() => api.health(), []);
  const [records, setRecords] = useState<ExperimentRecord[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    let alive = true;
    async function update() {
      try {
        const records = await experiments.list();
        if (!alive) return;
        setRecords(records);
        setError(null);
      } catch (error) {
        if (alive) setError(error as Error);
      }
    }
    void update();
    const timer = window.setInterval(update, 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);
  return (
    <>
      <header className="page-head">
        <h1>Your experiments</h1>
        <p>Each run keeps its own dataset, settings, logs and evidence. The recorded benchmark is separate.</p>
      </header>
      <div className="actions">
        <Link className="button primary" to="/new?source=sample">
          Run sample
        </Link>
        {health.data?.can_upload && (
          <Link className="button" to="/new?source=upload">
            Upload data
          </Link>
        )}
      </div>
      <StateBlock loading={!records && !error} error={error}>
        {records?.length ? (
          <div className="experiment-list">
            {records.map((r) => (
              <Link
                key={r.experiment_id}
                to={`/experiments/${r.experiment_id}${r.status === "completed" ? "/comparison" : ""}`}
              >
                <div>
                  <strong>{r.name}</strong>
                  <p>
                    {r.source === "synthetic" ? "Synthetic" : "Uploaded"} ·{" "}
                    {new Date(r.created_at * 1000).toLocaleString()} · {r.experiment_id.slice(0, 8)}
                  </p>
                </div>
                <span>
                  <Badge tone={r.status === "completed" ? "ok" : "neutral"}>{r.status.replaceAll("_", " ")}</Badge>
                  <p>{duration(r.elapsed_seconds ?? 0)}</p>
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <Panel title="No experiments yet">
            <p>Start with the synthetic sample to try the entire workflow without a download.</p>
          </Panel>
        )}
      </StateBlock>
    </>
  );
}

export function ExperimentProgress() {
  return (
    <TrainingOnly>
      <Progress />
    </TrainingOnly>
  );
}
function Progress() {
  const { experimentId } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState<ExperimentRecord | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!experimentId) return;
    const id = experimentId;
    let alive = true;
    async function update() {
      try {
        const record = await experiments.get(id);
        if (!alive) return;
        setRecord(record);
        setError("");
        if (record.status === "completed") navigate(`/experiments/${id}/comparison`, { replace: true });
      } catch (error) {
        if (alive) setError(errorMessage(error));
      }
    }
    void update();
    const timer = window.setInterval(update, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [experimentId, navigate]);
  async function cancel() {
    if (!experimentId) return;
    try {
      setRecord(await experiments.cancel(experimentId));
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  const stages = ["validating", "training", "selecting thresholds", "testing faults", "preparing results"];
  return (
    <>
      <header className="page-head">
        <h1>{record?.name ?? "Local experiment"}</h1>
        <p>
          Training runs in a separate worker. Refreshing this page will not stop it. Hosted runs need the same browser
          cookies to reopen.
        </p>
      </header>
      {error && (
        <div role="alert" className="state error">
          {error}
        </div>
      )}
      {!record && !error && <p role="status">Loading experiment…</p>}
      {record && (
        <Panel
          title={
            activeJob(record.status) ? "Experiment in progress" : `Experiment ${record.status.replaceAll("_", " ")}`
          }
          aside={<Badge>{record.source === "synthetic" ? "Synthetic data" : "Uploaded data"}</Badge>}
        >
          <p className="elapsed">{duration(record.elapsed_seconds ?? 0)} elapsed</p>
          <ol className="job-stages">
            {stages.map((stage) => (
              <li key={stage} aria-current={record.stage === stage ? "step" : undefined} className={stages.indexOf(stage) < stages.indexOf(record.stage ?? "") ? "stage-complete" : undefined}>
                {stage}
                {record.stage === stage && <strong> · current stage</strong>}
              </li>
            ))}
          </ol>
          <p role="status">
            {record.completed_work ?? 0}
            {record.total_work ? ` / ${record.total_work}` : ""}{" "}
            {record.work_unit || "completed work items in this stage"}
          </p>
          <p className="note">
            These counts report actual work. Runtime depends on hardware and data; no completion estimate is assumed.
          </p>
          {record.error && (
            <p className="state error" role="alert">
              {record.error}
            </p>
          )}
          {activeJob(record.status) ? (
            <Button variant="secondary" disabled={record.status === "cancelling"} onClick={cancel}>
              {record.status === "cancelling" ? "Cancelling…" : "Cancel experiment"}
            </Button>
          ) : (
            <Link
              className="button primary"
              to={`/new?source=${record.source === "synthetic" ? "sample" : "upload"}&dataset=${record.dataset_id}`}
            >
              Set up another run with this dataset
            </Link>
          )}
          <p className="note">
            Experiment {record.experiment_id} · configuration {record.config_fingerprint}
          </p>
        </Panel>
      )}
    </>
  );
}
