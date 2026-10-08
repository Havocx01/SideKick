import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, experiments } from "../api/client";
import type { ColumnMapping, DatasetRegistration, ExperimentRecord, ExperimentProtocol, PilotBrief } from "../api/types";
import { defaultProtocol, PilotBriefEditor, ProtocolEditor } from "../components/ProtocolEditor";
import { Badge, Button, Field, Panel, Select, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { useAnalysis } from "../components/AnalysisProvider";
import { AlertCircle, ArrowRight, Check, Circle, Clock3, FlaskConical, Layers, LoaderCircle, Upload } from "lucide-react";
import { NumberField } from "@/registry/components/number-field/number-field";
import { Progress as ArcProgress } from "@/components/arc/progress/progress";
import { CsvAttachment } from "../components/CsvAttachment";
import { observeTraining } from "../components/TrainingNotifications";
import { integer, percent } from "../format";

export const activeJob = (status: string) => ["queued", "running", "cancelling"].includes(status);
function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.detail || error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Try again.";
}
const duration = (seconds: number) => `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;

function minimumUploadDisplay(signal: AbortSignal) {
  return new Promise<void>(resolve => {
    function finish() {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    }
    const timer = window.setTimeout(finish, 3000);
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted) finish();
  });
}

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
          <h1 id="welcome-heading">Will warnings survive sensor faults?</h1>
          <p>Train failure-warning models. Test them with missing, stuck or drifting readings.</p>
          <div className="hero-actions">
            <Link className="button contrast" to="/walkthrough?step=clean">Start guided walkthrough <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
          <p className="hero-footnote">5 steps · Recorded results</p>
        </div>
        <div className="benchmark-preview">
          <div className="preview-heading"><h2>Warnings in time</h2><Badge>Recorded NASA Benchmark</Badge></div>
          <div className="preview-subtitle">Logistic regression · lr2</div>
          <StateBlock loading={selection.loading} error={selection.error}>
            {example ? (
              <>
                <div className="benchmark-bars">
                  <div>
                    <div className="benchmark-bar-label"><span>Healthy sensors</span><strong>{integer(example.clean.detected)} / {integer(example.clean.engines)}</strong></div>
                    <div className="benchmark-track" aria-hidden="true"><span style={{ width: percent(example.clean.detection_fraction) }} /></div>
                  </div>
                  <div>
                    <div className="benchmark-bar-label"><span>Weakest sensor fault</span><strong>{example.worst_metrics ? `${integer(example.worst_metrics.detected)} / ${integer(example.worst_metrics.engines)}` : percent(example.worst_detection_required)}</strong></div>
                    <div className="benchmark-track fault" aria-hidden="true"><span style={{ width: percent(example.worst_detection_required) }} /></div>
                  </div>
                </div>
                {/* <div className="preview-explanation">
                  <details><summary>What was tested?</summary><p>{scenarioLabel(example.worst_scenario_id ?? "")}. Warnings active 10–30 cycles before failure. Simulated NASA data, not ABB field validation.</p></details>
                  <Link to="/comparison?candidate=logistic_regression%2Flr2">Inspect the evidence <ArrowRight size={16} aria-hidden="true" /></Link>
                </div> */}
              </>
            ) : <p className="note">Open the recorded comparison to inspect the available candidates and fault tests.</p>}
          </StateBlock>
        </div>
      </section>
      <section className="start-section" aria-labelledby="start-heading">
        <h2 id="start-heading">Start an experiment</h2>
        <StateBlock loading={health.loading} error={health.error}>
          <div className="start-actions">
            <section>
              <div className="start-option"><Layers size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Recorded benchmark</h3><p>NASA data</p></div></div>
              <Link className="button" to="/comparison">Explore benchmark <ArrowRight size={16} aria-hidden="true" /></Link>
            </section>
            <section>
              <div className="start-option"><FlaskConical size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Sample experiment</h3><p>{health.data?.sample_equipment ?? 60} simulated histories</p></div></div>
              {health.data?.can_train ? <Link className="button" to="/new?source=sample">Set up sample <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
            <section>
              <div className="start-option"><Upload size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Your data</h3><p>CSV · Up to 10 MB · Complete failure histories</p></div></div>
              {health.data?.can_upload ? <Link className="button" to="/new?source=upload">Upload CSV <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
          </div>
        </StateBlock>
      </section>
      <p className="scope-note">Development evidence · Not field validated</p>
      {health.data?.mode === "demo" && <details><summary>Hosted sample limits</summary><p className="note">30 short histories, three sensors and four configurations. Two runs per browser per hour, one active server run, and shared daily limits apply. Results expire after 24 hours or sooner after a restart. Export evidence to keep it.</p></details>}
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
  const analysis = useAnalysis();
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
  const [attachment, setAttachment] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<"uploading" | "ready" | "error">("ready");
  const uploadController = useRef<AbortController | null>(null);
  const csvInput = useRef<HTMLInputElement>(null);
  const [burden, setBurden] = useState(10);
  const [protocol, setProtocol] = useState<ExperimentProtocol>(defaultProtocol([]));
  const [pilotBrief, setPilotBrief] = useState<PilotBrief>({ data_classification: "unverified" });
  const datasetId = params.get("dataset");
  const isSample = params.get("source") === "sample";
  useEffect(() => () => uploadController.current?.abort(), []);
  function receive(value: DatasetRegistration) {
    setData(value);
    setComplete(value.complete_histories ?? false);
    setMapping(value.mapping ?? { equipment_id: "", cycle_index: "", sensors: [], failure_cycle: null });
    if (value.confirmed) setProtocol(defaultProtocol((value.profile?.sensors ?? []).filter(s => s.varies).map(s => s.name)));
    if (value.source === "synthetic") setPilotBrief({ data_classification: "simulated" });
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
    if (file) setAttachment(file);
    if (file && file.size > 10 * 1024 * 1024) {
      setError("CSV files must be 10 MB or smaller.");
      setUploadState("error");
      return;
    }
    const controller = file ? new AbortController() : null;
    uploadController.current = controller;
    if (file) setUploadState("uploading");
    setBusy(true);
    setError("");
    const minimumDisplay = controller ? minimumUploadDisplay(controller.signal) : undefined;
    try {
      const value = file ? await experiments.upload(file, controller!.signal) : await experiments.sample();
      await minimumDisplay;
      if (controller?.signal.aborted) return;
      if (file) setUploadState("ready");
      receive(value);
      setParams({ source: file ? "upload" : "sample", dataset: value.dataset_id }, { replace: true });
    } catch (e) {
      await minimumDisplay;
      if (controller?.signal.aborted) return;
      if (file) setUploadState("error");
      setError(errorMessage(e));
    } finally {
      if (uploadController.current === controller) {
        uploadController.current = null;
        setBusy(false);
      }
    }
  }
  function removeAttachment() {
    uploadController.current?.abort();
    uploadController.current = null;
    setAttachment(null); setUploadState("ready"); setError(""); setBusy(false);
    setData(null); setMapping(null); setComplete(false);
    setParams({ source: "upload" }, { replace: true });
    requestAnimationFrame(() => csvInput.current?.focus());
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
        , ...(health.data?.can_edit_protocol ? { protocol: { ...protocol, min_detection_fraction: detection / 100, max_early_alarm_burden: burden / 100 }, pilot_brief: pilotBrief } : {})
      });
      observeTraining(result, true);
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
  const invalidSettings = !Number.isFinite(detection) || !Number.isFinite(burden) || detection < 0 || detection > 100 || burden < 0 || burden > 100
    || Boolean(health.data?.can_edit_protocol && (!protocol.scenarios?.some(s => s.required !== false)
      || !((protocol.min_useful_lead ?? 10) < (protocol.horizon_cycles ?? 30) && (protocol.horizon_cycles ?? 30) < (protocol.transition_band_end ?? 45))));
  return (
    <div className="experiment-setup">
      <header className="page-head">
        <h1>{isSample ? "Run a sample experiment" : "Use your equipment histories"}</h1>
      </header>
      <ol className="setup-steps" aria-label="Data setup steps">
        {["Choose data", "Confirm mapping", "Train models"].map((step, index) => <li key={step} aria-current={index === (!data ? 0 : data.confirmed ? 2 : 1) ? "step" : undefined}><span className="step-number">{index + 1}</span>{step}</li>)}
      </ol>
      {error && !(attachment && uploadState === "error" && !data) && (
        <div className="state error" role="alert">
          {error} <Link to="/experiments">View your experiments</Link>
          {" · "}
          <Link to="/comparison">Explore recorded benchmark</Link>
        </div>
      )}
      {busy && uploadState !== "uploading" && <p role="status">Preparing your request. Please wait…</p>}
      {!data && (isSample ? (
        <Panel title="Generate a practice dataset">
          <p>
            {health.data?.sample_equipment ?? 60} simulated histories. Practice data, not field validation.{" "}
            {health.data?.mode === "demo" && "10 development histories; 20 reserved."}
          </p>
          <Button variant="primary" loading={busy} onClick={() => prepare()}>
            Generate sample data
          </Button>
        </Panel>
      ) : (
        <div className="csv-upload">
          <Panel title="Upload CSV">
            <div className="csv-upload-layout">
              <div className="csv-upload-main">
                {attachment ? <CsvAttachment name={attachment.name} size={attachment.size} state={uploadState} error={error} onRemove={removeAttachment} onRetry={attachment.size <= 10 * 1024 * 1024 ? () => void prepare(attachment) : undefined} /> : <label className="csv-file-picker">
                  <span className="csv-attachment-media"><Upload size={20} strokeWidth={1.75} aria-hidden="true" /></span>
                  <span><strong>Choose a CSV file</strong><small>CSV · Up to 10 MB</small></span>
                  <input
                    ref={csvInput}
                    type="file"
                    accept=".csv,text/csv"
                    aria-label="CSV file (up to 10 MB)"
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) void prepare(file);
                    }}
                  />
                </label>}
                <details className="csv-paste disclosure-plain">
                  <summary>Paste CSV instead</summary>
                  <Field label="CSV contents">
                    <textarea value={csvText} disabled={busy} onChange={event => setCsvText(event.target.value)} rows={8} placeholder={"equipment_id,cycle,sensor_1,failure_cycle\nengine_1,1,0.52,120"} />
                  </Field>
                  <Button disabled={busy || !csvText.trim()} loading={busy} onClick={() => prepare(new File([csvText], "pasted-histories.csv", { type: "text/csv" }))}>Use pasted CSV</Button>
                </details>
              </div>
              <aside className="csv-upload-requirements" aria-labelledby="csv-requirements-title">
                <h3 id="csv-requirements-title">Data requirements</h3>
                <dl>
                  <div><dt>Complete failure histories</dt><dd>25 minimum</dd></div>
                  <div><dt>Reserved for validation</dt><dd>20 histories</dd></div>
                </dl>
                <p className="note">UTF-8 · Unique headers<br />Whole-number cycles · Observed failures</p>
              </aside>
            </div>
          </Panel>
        </div>
      ))}
      {data && (
        <>
          {!data.confirmed && <Panel
            title={data.source === "upload" ? "Review attached CSV" : data.name}
            aside={
              <Badge tone={data.source === "synthetic" ? "warn" : "info"}>
                {data.source === "synthetic" ? "Synthetic demonstration" : "Uploaded data"}
              </Badge>
            }
          >
            {data.source === "upload" && <CsvAttachment name={data.name} size={attachment?.name === data.name ? attachment.size : undefined} state="ready" disabled={busy} onRemove={removeAttachment} />}
            <p className={data.source === "upload" ? "csv-attached-summary" : undefined}>
              {data.row_count.toLocaleString()} readings across {data.columns.length} columns.
            </p>
            <DatasetPreview data={data} />
          </Panel>}
          {!data.confirmed && mapping && (
            <Panel
              title="Confirm what each column means"
              description="IDs and failure targets cannot be sensor inputs."
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
                Histories without an observed failure are unsupported.
              </p>
              <div className="actions">{analysis.enabled("data") && <Button variant="secondary" disabled={busy} onClick={() => analysis.start({ task: "data", dataset_id: data.dataset_id,
                candidates: [], mapping, complete_histories: complete }, suggestion => { setMapping(suggestion); setError(""); })}>Review data</Button>}
              <Button variant="primary" loading={busy}
                disabled={
                  !mapping.equipment_id || !mapping.cycle_index || !mapping.sensors.length ||
                  (!mapping.failure_cycle && !complete)
                }
                onClick={confirm}
              >
                Validate and confirm mapping
              </Button>
              </div>
            </Panel>
          )}
          {data.confirmed && data.profile && data.splits && (
            <>
              <Panel title="Data ready" description={`${data.name} · ${data.row_count.toLocaleString()} readings · ${data.mapping?.sensors.length ?? 0} sensors`}
                aside={<Badge tone={data.source === "synthetic" ? "warn" : "info"}>{data.source === "synthetic" ? "Synthetic demonstration" : "Uploaded data"}</Badge>}>
                <div className="split-overview"><div><strong>{data.splits.development.length}</strong><span>Development · {data.splits.folds.length} folds</span></div><div><strong>{data.splits.holdout.length}</strong><span>Reserved · Unscored</span></div></div>
                {data.profile.findings?.some(finding => finding.severity !== "info") && <ul className="setup-data-warnings">{data.profile.findings.filter(finding => finding.severity !== "info").map(finding => <li key={finding.code}>{finding.message}</li>)}</ul>}
                <details className="setup-data-inspection disclosure-plain"><summary>Inspect data and equipment split</summary>
                <DatasetPreview data={data} />
                <details className="disclosure-plain">
                  <summary>Inspect equipment assignments</summary>
                  <p>Equipment stays separate across training and evaluation.</p>
                  <p>Reserved: {data.splits.holdout.join(", ")}</p>
                  {data.splits.folds.map((fold, i) => (
                    <p key={i}>
                      Validation fold {i + 1}: {fold.join(", ")}
                    </p>
                  ))}
                </details>
                <details className="disclosure-plain">
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
                <details className="disclosure-plain"><summary>Dataset identifiers</summary><p className="note">
                  Dataset fingerprint: <code>{data.profile.data_hash}</code>.{" "}
                  {health.data?.mode === "demo"
                    ? "The hosted sample has a fixed mapping. Use the local app for your own data."
                    : "This confirmed copy is fixed; upload another copy to change its mapping."}
                </p></details>
                </details>
              </Panel>
              <Panel
                title="Review the test"
                description="Demonstration defaults. Adjust to your equipment."
              >
                <dl className="setup-test-summary">
                  <div><dt>Warning window</dt><dd>{protocol.min_useful_lead ?? 10}–{protocol.horizon_cycles ?? 30} <span>cycles before failure</span></dd></div>
                  {health.data?.can_edit_protocol && <div><dt>Required faults</dt><dd>{protocol.scenarios?.filter(s => s.required !== false).length ?? 0} <span>sensor tests</span></dd></div>}
                  <div><dt>Minimum timely warnings</dt><dd>{detection}%</dd></div>
                  <div><dt>Max. early-alarm time</dt><dd>{burden}%</dd></div>
                </dl>
                <div className="experiment-protocol-sections">
                <section className="setup-advanced" aria-label="Adjust test settings"><h3>Adjust test settings</h3>
                <div className="mapping-roles">
                  <NumberField label="Minimum warned in time" value={detection} onValueChange={setDetection} min={0} max={100} suffix="%" disabled={busy} limitHint={false} />
                  <NumberField label="Maximum early-alarm time" value={burden} onValueChange={setBurden} min={0} max={100} suffix="%" disabled={busy} limitHint={false} />
                </div>
                {health.data?.can_edit_protocol ? <ProtocolEditor value={protocol} onChange={setProtocol} sensors={data.mapping?.sensors ?? []} disabled={busy} /> : <p className="note">Useful warnings: 10 to 30 cycles before failure. Early-alarm burden: time in alarm more than 45 cycles before failure.</p>}
                <p className="note setup-training-note">
                  Fixed for this version: five equipment folds, {health.data?.sample_configurations ?? 10} candidate
                  configurations and a 20-cycle feature window. Final validation is a separate, explicit local action.
                </p>
                </section>
                {health.data?.can_edit_protocol && <PilotBriefEditor value={pilotBrief} onChange={setPilotBrief} disabled={busy} />}
                </div>
                {invalidSettings && <p className="setup-settings-error" role="alert">Check the test limits and warning-window order in Adjust test settings.</p>}
                <div className="experiment-start-actions">
                <Button variant="primary" loading={busy}
                  disabled={invalidSettings}
                  onClick={start}
                >
                  Train and challenge models
                </Button>
                <p className="note">
                  One run at a time · 15-minute limit
                </p>
                </div>
              </Panel>
            </>
          )}
        </>
      )}
    </div>
  );
}

function DatasetPreview({ data }: { data: DatasetRegistration }) {
  return <details className="disclosure-plain"><summary>Preview the first {data.preview.length} rows</summary>
    <div className="table-scroll"><table><thead><tr>{data.columns.map(column => <th key={column}>{column}</th>)}</tr></thead>
      <tbody>{data.preview.map((row, index) => <tr key={index}>{data.columns.map(column => <td key={column} title={String(row[column] ?? "missing")}>{row[column] === null ? "missing" : typeof row[column] === "number" ? row[column].toLocaleString(undefined, { maximumFractionDigits: 3 }) : String(row[column])}</td>)}</tr>)}</tbody>
    </table></div>
  </details>;
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
  const [cancelBusy, setCancelBusy] = useState(false);
  useEffect(() => {
    if (!experimentId) return;
    const id = experimentId;
    let alive = true;
    async function update() {
      try {
        const record = await experiments.get(id);
        if (!alive) return;
        setRecord(record);
        observeTraining(record);
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
    setCancelBusy(true);
    try {
      setRecord(await experiments.cancel(experimentId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCancelBusy(false);
    }
  }
  const stages = record?.job_kind === "freeze"
    ? [["validating", "Validate data"], ["refitting selected model", "Refit selected model"], ["preparing frozen model", "Prepare frozen model"]]
    : record?.job_kind === "validation"
      ? [["validating", "Validate data"], ["testing reserved equipment", "Test reserved equipment"]]
      : [["validating", "Validate data"], ["training", "Train models"], ["selecting thresholds", "Set thresholds"], ["testing faults", "Test sensor faults"], ["preparing results", "Prepare results"]];
  const currentStage = stages.findIndex(([stage]) => stage === record?.stage);
  const hasTotal = Boolean(record?.total_work && record.total_work > 0);
  const workCount = record?.completed_work ?? 0;
  const workText = hasTotal ? `${workCount} / ${record?.total_work} ${record?.work_unit || "work items completed"}`
    : workCount > 0 ? `${workCount} ${record?.work_unit || "work items completed"}`
      : record?.work_unit || (record?.status === "queued" ? "Waiting to start" : "Work count unavailable for this stage.");
  return (
    <div className="experiment-progress">
      <header className="page-head">
        <h1>{record?.name ?? "Local experiment"}</h1>
      </header>
      {error && (
        <div role="alert" className="state error">
          {error}
        </div>
      )}
      {!record && !error && <p role="status">Loading experiment...</p>}
      {record && (
        <Panel
          title={
            record.status === "queued" ? "Experiment queued" : record.status === "cancelling" ? "Cancelling experiment"
              : activeJob(record.status) ? "Experiment in progress" : `Experiment ${record.status.replaceAll("_", " ")}`
          }
          aside={<Badge>{record.source === "synthetic" ? "Synthetic data" : "Uploaded data"}</Badge>}
        >
          <div className="run-timing"><Clock3 size={16} aria-hidden="true" /><span className="elapsed">{duration(record.elapsed_seconds ?? 0)}</span><span>elapsed</span></div>
          <ol className="job-stages" aria-label="Experiment stages">
            {stages.map(([stage, label], index) => {
              const current = index === currentStage;
              const done = index < currentStage;
              const running = current && record.status === "running";
              const stopped = current && !activeJob(record.status);
              const failed = stopped && record.status !== "cancelled";
              return <li key={stage} aria-current={current ? "step" : undefined} className={done ? "stage-complete" : stopped ? "stage-stopped" : undefined}>
                <span className="job-stage-mark" aria-hidden="true">{done ? <Check size={20} /> : running ? <LoaderCircle className="run-spinner" size={20} /> : failed ? <AlertCircle size={20} /> : current ? <Clock3 size={20} /> : <Circle size={12} />}</span>
                <span>{label}</span><span className="sr-only">{done ? "Completed" : current ? running ? "In progress" : record.status.replaceAll("_", " ") : "Not started"}</span>
              </li>;
            })}
          </ol>
          {currentStage === -1 && record.stage && record.status !== "queued" && <p className="note run-unlisted-stage">Current stage: {record.stage}</p>}
          <div className="run-work-progress" role="status" aria-live="polite">
            {hasTotal ? <ArcProgress label={`Current stage: ${workText}`} value={workCount} max={record.total_work!} /> : <p className="note">{workText}</p>}
          </div>
          {record.error && (
            <p className="state error" role="alert">
              {record.error}
            </p>
          )}
          <div className="run-actions">
          {activeJob(record.status) ? (
            <Button variant="secondary" loading={cancelBusy} disabled={record.status === "cancelling"} onClick={cancel}>
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
          {activeJob(record.status) && <p className="note">Runs continue if you refresh.</p>}
          </div>
          <details className="run-identifiers disclosure-plain"><summary>Run identifiers</summary><dl>
            <div><dt>Experiment</dt><dd><code>{record.experiment_id}</code></dd></div>
            <div><dt>Configuration</dt><dd><code>{record.config_fingerprint}</code></dd></div>
          </dl></details>
        </Panel>
      )}
    </div>
  );
}
