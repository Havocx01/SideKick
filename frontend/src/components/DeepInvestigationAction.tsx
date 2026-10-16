import { useEffect, useId, useRef, useState } from "react";
import { Cpu, X } from "lucide-react";
import { Input } from "@/components/arc/input/input";
import { Textarea } from "@/components/arc/textarea/textarea";
import type { AnalysisRequest, ExperimentEngineerContext } from "../api/types";
import { assistant } from "../api/assistant";
import { experiments } from "../api/client";
import { demoPrefill, prefillEngineerContext } from "../lib/demo-prefill";
import { analysisError, useAnalysis } from "./AnalysisProvider";
import { Button, IconButton } from "./Chrome";
import styles from "./deep-investigation-setup.module.css";

const emptyContext: ExperimentEngineerContext = { equipment_type: "", sensor_meaning: "", decision: "" };
const clean = (value: ExperimentEngineerContext) => Object.fromEntries(Object.entries(value).map(([key, text]) => [key, text?.trim() ?? ""]));

/** Read/edit shared metadata locally. Only Start admits an AI analysis request. */
export function DeepInvestigationAction({ context }: { context: AnalysisRequest }) {
  const analysis = useAnalysis();
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<ExperimentEngineerContext | null>(null);
  const [fields, setFields] = useState<ExperimentEngineerContext>(emptyContext);
  const [focus, setFocus] = useState(context.investigation_focus ?? "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [saveNotice, setSaveNotice] = useState("");
  const [demo, setDemo] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLSpanElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const id = useId();
  const dirty = saved !== null && JSON.stringify(clean(fields)) !== JSON.stringify(clean(saved));
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal(); title.current?.focus();
    let current = true;
    Promise.all([
      assistant.experimentContext(context.experiment_id),
      context.experiment_id ? experiments.get(context.experiment_id).catch(() => null) : Promise.resolve(null)
    ]).then(([value, run]) => {
      if (current) {
        const preset = run ? demoPrefill(run) : null;
        setSaved(value); setFields(preset ? prefillEngineerContext(value, preset.context) : value); setError("");
        setDemo(Boolean(preset));
        if (preset) setFocus(current => current.trim() ? current : preset.focus);
      }
    }, failure => { if (current) setError(analysisError(failure)); });
    return () => { current = false; };
  }, [open, revision, context.experiment_id]);
  function close() {
    if (busy) return;
    setOpen(false);
    requestAnimationFrame(() => opener.current?.querySelector("button")?.focus());
  }
  async function save() {
    setBusy(true); setError(""); setSaveNotice("");
    try {
      const value = await assistant.saveExperimentContext(context.experiment_id, fields);
      setSaved(value); setFields(value); setSaveNotice("Context saved for this experiment.");
    } catch (failure) { setError(analysisError(failure)); }
    finally { setBusy(false); }
  }
  function start() {
    if (!saved || busy || dirty) return;
    dialog.current?.close();
    setOpen(false);
    opener.current?.querySelector("button")?.focus();
    analysis.start({ ...context, task: "deep", engineer_context: Object.values(saved).some(Boolean) ? saved : undefined,
      investigation_focus: focus.trim() || undefined });
  }
  return <>
    <span ref={opener}><Button variant="secondary" aria-haspopup="dialog" onClick={() => { setSaved(null); setError(""); setSaveNotice(""); setOpen(true); }}><Cpu size={15} aria-hidden="true" />Deep investigation</Button></span>
    {open && <dialog ref={dialog} className={styles.dialog} aria-labelledby={id} onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <header><h2 id={id} ref={title} tabIndex={-1}>Plan an investigation</h2><IconButton label="Close investigation setup" disabled={busy} onClick={close}><X size={17} aria-hidden="true" /></IconButton></header>
      <p className="note">Explore possible explanations and checks using recorded development evidence. No training or validation runs are started.</p>
      {demo && <p className="note">Demo text is prefilled. Review and save the context before starting.</p>}
      <Textarea label="What should this investigation focus on? (optional)" placeholder="For example, why missing readings delay warnings" maxLength={500} rows={2} value={focus} onChange={event => setFocus(event.target.value)} />
      {saved ? <details className={styles.context} open={demo}><summary>Experiment context{Object.values(saved).some(Boolean) ? " · Saved" : " · Optional"}</summary>
        <p className="note">Saved with this experiment and shared with AI when you start an investigation. These descriptions do not affect training or scoring. Contact details and other pilot notes are excluded.</p>
        <div className={styles.fields}>
          <Input label="Equipment type" maxLength={200} disabled={busy} value={fields.equipment_type ?? ""} onChange={event => { setSaveNotice(""); setFields(previous => ({ ...previous, equipment_type: event.target.value })); }} />
          <Textarea label="What the sensors measure" maxLength={500} rows={2} disabled={busy} value={fields.sensor_meaning ?? ""} onChange={event => { setSaveNotice(""); setFields(previous => ({ ...previous, sensor_meaning: event.target.value })); }} />
          <Textarea label="Decision the experiment supports" maxLength={2000} rows={2} disabled={busy} value={fields.decision ?? ""} onChange={event => { setSaveNotice(""); setFields(previous => ({ ...previous, decision: event.target.value })); }} />
        </div>
        <div className={styles.save}><Button size="sm" variant="secondary" disabled={busy || !dirty} onClick={save}>{busy ? "Saving context…" : "Save context"}</Button>{dirty && <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setFields(saved); setError(""); }}>Cancel edit</Button>}<span role="status">{saveNotice}</span></div>
      </details> : !error && <p role="status" className="note">Loading saved context…</p>}
      {error && <div role="alert" className="analysis-error"><p>{error}</p>{!saved && <Button variant="secondary" size="sm" onClick={() => { setError(""); setRevision(value => value + 1); }}>Retry loading context</Button>}</div>}
      {dirty && <p className="note" role="status">Save your context changes or cancel the edit before starting.</p>}
      <footer><span className="note">Saved answers are reused. A new investigation uses one AI request.</span><Button disabled={!saved || busy || dirty} onClick={start}>Start investigation</Button></footer>
    </dialog>}
  </>;
}
