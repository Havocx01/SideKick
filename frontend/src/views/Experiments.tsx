import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, experiments } from "../api/client";
import type { ColumnMapping, DatasetRegistration, ExperimentRecord } from "../api/types";
import { Badge, Field, Panel, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";

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
  return (
    <>
      <header className="page-head welcome">
        <p className="intro-label">Sidekick · Model cross-examiner</p>
        <h1>Would your failure warnings survive a faulty sensor?</h1>
        <p>
          Sidekick trains models on equipment histories, challenges them with missing, frozen and drifting sensor
          readings, and shows which candidates still meet your requirements.
        </p>
      </header>
      <nav className="mobile-paths" aria-label="Choose how to start">
        <Link to="/comparison">Recorded benchmark</Link>
        {health.data?.can_train ? (
          <Link to="/new?source=sample">Synthetic sample</Link>
        ) : (
          <span>Synthetic sample · local only</span>
        )}
        {health.data?.can_upload ? (
          <Link to="/new?source=upload">Upload CSV</Link>
        ) : (
          <span>Upload CSV · local only</span>
        )}
      </nav>
      <div className="journey" aria-label="Experiment workflow">
        Choose data <span>→</span> Check it <span>→</span> Train and challenge <span>→</span> Inspect results{" "}
        <span>→</span> Export evidence
      </div>
      <StateBlock loading={health.loading} error={health.error}>
        <div className="start-actions">
          <section>
            <div>
              <Badge tone="info">Recorded NASA results</Badge>
              <h2>Explore the benchmark</h2>
              <p>
                See a finished evaluation and replay how a sensor fault changes one engine’s warnings. No training
                required.
              </p>
            </div>
            <Link className="button" to="/comparison">
              Explore benchmark
            </Link>
          </section>
          <section>
            <div>
              <Badge tone="warn">Synthetic data</Badge>
              <h2>Run a sample experiment</h2>
              <p>
                Generate {health.data?.sample_equipment ?? 60} simulated equipment histories and run real training. No
                dataset download needed.
              </p>
            </div>
            {health.data?.can_train ? (
              <Link className="button primary" to="/new?source=sample">
                Run sample experiment
              </Link>
            ) : (
              <button disabled>Available in the local app</button>
            )}
          </section>
          <section>
            <div>
              <Badge>Local CSV</Badge>
              <h2>Upload your data</h2>
              <p>
                Use complete run-to-failure histories with equipment IDs, cycle indices and numeric sensor readings. Up
                to 10 MB.
              </p>
            </div>
            {health.data?.can_upload ? (
              <Link className="button" to="/new?source=upload">
                Upload your data
              </Link>
            ) : (
              <button disabled>Available in the local app</button>
            )}
          </section>
        </div>
      </StateBlock>
      {health.data?.mode === "demo" && (
        <p className="scope-note">
          Hosted samples use real server training. Two runs per browser per hour, with one active run across the server.
          The hosted sample uses 30 short histories, three sensors and four model configurations to fit free hosting.
          Results belong to this browser and expire after 24 hours; server restarts or idle shutdowns may clear them
          sooner. Export evidence to keep it. Shared daily limits also apply. The recorded benchmark stays available.
        </p>
      )}
      <p className="scope-note">
        A passing result supports further evaluation. Sidekick does not approve deployment, monitor live equipment, or
        establish field performance on ABB assets.
      </p>
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
    <Field label={label}>
      <select
        disabled={busy}
        value={mapping?.[key] ?? ""}
        onChange={(e) =>
          setMapping((m) => m && { ...m, [key]: e.target.value || (key === "failure_cycle" ? null : "") })
        }
      >
        <option value="">{key === "failure_cycle" ? "No failure-cycle column" : "Choose a column"}</option>
        {data?.columns.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </Field>
  );
  return (
    <>
      <header className="page-head">
        <h1>{isSample ? "Run a sample experiment" : "Use your equipment histories"}</h1>
        <p>Check the data, choose your acceptance limits, then train and challenge the models.</p>
      </header>
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
              <button className="primary" disabled={busy} onClick={() => prepare()}>
                Generate sample data
              </button>
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
                    if (file) void prepare(file);
                  }}
                />
              </Field>
              <p className="note">
                Use UTF-8 CSV with unique headers. This version supports operating cycles and complete histories, not
                hours-based targets or machines that have not failed.
              </p>
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
              {data.row_count.toLocaleString()} readings. Previewing the first {data.preview.length} rows.
            </p>
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
                      {data.columns.map((c) => (<td key={c}>{row[c] === null ? "missing" : String(row[c])}</td>))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          {!data.confirmed && mapping && (
            <Panel
              title="Confirm what each column means"
              description="Suggested roles are only a starting point. Choose sensors deliberately so targets and identifiers do not become model inputs."
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
              <button
                className="primary"
                disabled={
                  busy || !mapping.equipment_id || !mapping.cycle_index || !mapping.sensors.length ||
                  (!mapping.failure_cycle && !complete)
                }
                onClick={confirm}
              >
                Validate and confirm mapping
              </button>
            </Panel>
          )}
          {data.confirmed && data.profile && data.splits && (
            <>
              <Panel title="Data checked. Review the equipment split.">
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
                  <Field label="Minimum useful detection (%)">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      value={detection}
                      onChange={(e) => setDetection(e.target.valueAsNumber)}
                    />
                  </Field>
                  <Field label="Maximum early-alarm burden (%)">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="1"
                      value={burden}
                      onChange={(e) => setBurden(e.target.valueAsNumber)}
                    />
                  </Field>
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
                <button
                  className="primary"
                  disabled={
                    busy || !Number.isFinite(detection) || !Number.isFinite(burden) || detection < 0 || detection > 100 ||
                    burden < 0 ||
                    burden > 100
                  }
                  onClick={start}
                >
                  Train and challenge models
                </button>
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
          <Panel title="No experiments in this browser yet">
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
              <li key={stage} aria-current={record.stage === stage ? "step" : undefined}>
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
            <button disabled={record.status === "cancelling"} onClick={cancel}>
              {record.status === "cancelling" ? "Cancelling…" : "Cancel experiment"}
            </button>
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
