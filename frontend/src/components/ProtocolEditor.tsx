import { useState } from "react";
import type { ExperimentProtocol, FaultSpec, FaultScenario, PilotBrief } from "../api/types";
import { Button, Select } from "./Chrome";
import { NumberField } from "@/registry/components/number-field/number-field";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";

export function defaultProtocol(sensors: string[]): ExperimentProtocol {
  return { version: 1, min_useful_lead: 10, horizon_cycles: 30, transition_band_end: 45,
    min_detection_fraction: .7, max_early_alarm_burden: .1, base_seed: 20260918,
    scenarios: sensors.flatMap(sensor => [
      { fault: { sensor, kind: "dropout", duration: "persistent", onset_before_failure: 60 }, required: true },
      { fault: { sensor, kind: "stuck", duration: "persistent", onset_before_failure: 60 }, required: true },
      ...[-1, 1].map(sign => ({ fault: { sensor, kind: "drift" as const, duration: "persistent" as const,
        onset_before_failure: 60, severity_sd: 1, sign, ramp_cycles: 20 }, required: true }))
    ] as FaultScenario[]) };
}

export function ProtocolEditor({ value, onChange, sensors, disabled }: { value: ExperimentProtocol; onChange: (value: ExperimentProtocol) => void; sensors: string[]; disabled: boolean }) {
  const [draft, setDraft] = useState<FaultSpec>({ sensor: sensors[0] ?? "", kind: "dropout", duration: "persistent", onset_before_failure: 60 });
  const [required, setRequired] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");
  const scenarios = value.scenarios ?? [];
  const update = (field: keyof ExperimentProtocol, number: number) => onChange({ ...value, [field]: number });
  function save() {
    if (!draft.sensor || !Number.isInteger(draft.onset_before_failure) || (draft.onset_before_failure ?? 0) < (value.min_useful_lead ?? 10)) {
      setError("Choose a sensor and an onset at or before the minimum useful lead."); return;
    }
    const fault: FaultSpec = { sensor: draft.sensor, kind: draft.kind, duration: draft.duration,
      onset_before_failure: draft.onset_before_failure,
      ...(draft.duration === "transient" ? { length: draft.length ?? 10 } : {}),
      ...(draft.kind === "drift" ? { severity_sd: draft.severity_sd ?? 1, sign: draft.sign ?? 1, ramp_cycles: draft.ramp_cycles ?? 20 } : {}) };
    const entry = { fault, required };
    const next = editing == null ? [...scenarios, entry] : scenarios.map((s, i) => i === editing ? entry : s);
    onChange({ ...value, scenarios: next }); setEditing(null); setError("");
  }
  return <div className="protocol-editor">
    <div className="mapping-roles">
      <NumberField label="Minimum useful lead" value={value.min_useful_lead ?? 10} onValueChange={n => update("min_useful_lead", n)} min={1} disabled={disabled} suffix=" cycles" />
      <NumberField label="Warning horizon" value={value.horizon_cycles ?? 30} onValueChange={n => update("horizon_cycles", n)} min={2} disabled={disabled} suffix=" cycles" />
      <NumberField label="Early-alarm boundary" value={value.transition_band_end ?? 45} onValueChange={n => update("transition_band_end", n)} min={3} disabled={disabled} suffix=" cycles" />
    </div>
    <p className="note">Minimum lead must be below the horizon, and the early-alarm boundary above it. All durations are operating cycles.</p>
    <details className="decision-detail"><summary>Sensor fault scenarios ({scenarios.length}, {scenarios.filter(s => s.required !== false).length} required)</summary>
      <div className="table-scroll"><table><thead><tr><th>Sensor</th><th>Fault</th><th>Onset</th><th>Required</th><th>Actions</th></tr></thead><tbody>{scenarios.map((s, i) => <tr key={i}>
        <td>{s.fault.sensor}</td><td>{s.fault.kind}{s.fault.kind === "drift" ? ` ${s.fault.sign === -1 ? "down" : "up"} ${s.fault.severity_sd} SD` : ""}<span className="note comparison-kind">{s.fault.duration}{s.fault.duration === "transient" ? `, ${s.fault.length} cycles` : ""}</span></td><td>{s.fault.onset_before_failure} cycles out</td>
        <td><label className="scenario-required"><input type="checkbox" aria-label={`Require scenario ${i + 1}: ${s.fault.sensor} ${s.fault.kind}`} disabled={disabled} checked={s.required !== false} onChange={e => onChange({ ...value, scenarios: scenarios.map((entry, index) => index === i ? { ...entry, required: e.target.checked } : entry) })} /></label></td>
        <td><div className="scenario-actions"><Button variant="ghost" disabled={disabled} onClick={() => { setDraft(s.fault); setRequired(s.required !== false); setEditing(i); }}>Edit case {i + 1}</Button><Button variant="ghost" disabled={disabled} onClick={() => { onChange({ ...value, scenarios: scenarios.filter((_, index) => index !== i) }); setEditing(null); }}>Remove case {i + 1}</Button></div></td>
      </tr>)}</tbody></table></div>
      <section className="fault-builder"><h3>{editing == null ? "Add a fault case" : `Edit fault case ${editing + 1}`}</h3>
        <div className="mapping-roles">
          <Select label="Sensor" value={draft.sensor} disabled={disabled} options={sensors.map(sensor => ({ value: sensor, label: sensor }))} onValueChange={sensor => setDraft({ ...draft, sensor })} />
          <Select label="Fault" value={draft.kind} disabled={disabled} options={[{ value: "dropout", label: "Dropout" }, { value: "stuck", label: "Stuck reading" }, { value: "drift", label: "Drift" }]} onValueChange={kind => setDraft({ ...draft, kind: kind as FaultSpec["kind"] })} />
          <Select label="Duration" value={draft.duration} disabled={disabled} options={[{ value: "persistent", label: "Persistent" }, { value: "transient", label: "Transient" }]} onValueChange={duration => setDraft({ ...draft, duration: duration as FaultSpec["duration"] })} />
          <NumberField label="Onset before failure" value={draft.onset_before_failure ?? 60} min={1} disabled={disabled} onValueChange={onset_before_failure => setDraft({ ...draft, onset_before_failure })} />
          {draft.duration === "transient" && <NumberField label="Fault length" value={draft.length ?? 10} min={1} disabled={disabled} onValueChange={length => setDraft({ ...draft, length })} />}
          {draft.kind === "drift" && <><NumberField label="Drift severity (training SD)" value={draft.severity_sd ?? 1} step={.1} min={.1} max={100} disabled={disabled} onValueChange={severity_sd => setDraft({ ...draft, severity_sd })} /><NumberField label="Drift ramp" value={draft.ramp_cycles ?? 20} min={1} disabled={disabled} onValueChange={ramp_cycles => setDraft({ ...draft, ramp_cycles })} /><Select label="Drift direction" value={String(draft.sign ?? 1)} disabled={disabled} options={[{ value: "1", label: "Up" }, { value: "-1", label: "Down" }]} onValueChange={sign => setDraft({ ...draft, sign: Number(sign) })} /></>}
        </div>
        <label className="confirmation"><input type="checkbox" checked={required} disabled={disabled} onChange={e => setRequired(e.target.checked)} />Required for qualification</label>
        {error && <p role="alert" className="state error">{error}</p>}
        <Button disabled={disabled || (editing == null && scenarios.length >= 128)} onClick={save}>{editing == null ? "Add fault scenario" : "Save fault scenario"}</Button>
        {editing != null && <Button variant="ghost" onClick={() => setEditing(null)}>Cancel case edit</Button>}
      </section>
    </details>
    <p className="note">Required cases must cover every evaluated history. Supplemental cases are exploratory. Maximum 128 scenarios.</p>
  </div>;
}

export function PilotBriefEditor({ value, onChange, disabled }: { value: PilotBrief; onChange: (value: PilotBrief) => void; disabled: boolean }) {
  return <details className="decision-detail"><summary>Pilot brief (optional)</summary><div className="pilot-brief-fields">
    <Input label="Equipment family" value={value.equipment_family ?? ""} maxLength={200} disabled={disabled} onChange={e => onChange({ ...value, equipment_family: e.target.value })} />
    <Input label="Reviewing engineer" value={value.reviewing_engineer ?? ""} maxLength={200} disabled={disabled} onChange={e => onChange({ ...value, reviewing_engineer: e.target.value })} />
    <Select label="Data classification" value={value.data_classification ?? "unverified"} disabled={disabled} options={[{ value: "simulated", label: "Simulated benchmark" }, { value: "field", label: "Field records (user declared)" }, { value: "unverified", label: "Unverified" }]} onValueChange={data_classification => onChange({ ...value, data_classification: data_classification as PilotBrief["data_classification"] })} />
    <Textarea label="Current review procedure" value={value.current_procedure ?? ""} maxLength={2000} rows={3} disabled={disabled} onChange={e => onChange({ ...value, current_procedure: e.target.value })} />
    <Textarea label="Decision this review supports" value={value.intended_decision ?? ""} maxLength={2000} rows={3} disabled={disabled} onChange={e => onChange({ ...value, intended_decision: e.target.value })} />
    <Input label="Proposed success measure" value={value.success_measure ?? ""} maxLength={1000} disabled={disabled} onChange={e => onChange({ ...value, success_measure: e.target.value })} />
  </div><p className="note">Field validation needs actual equipment records and an agreed review decision. This brief records intentions, not measured benefits.</p></details>;
}
