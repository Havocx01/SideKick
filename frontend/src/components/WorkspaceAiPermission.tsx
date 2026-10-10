import { useEffect, useRef, useState } from "react";
import { Cpu, X } from "lucide-react";
import { assistant } from "../api/assistant";
import type { ConsentState } from "../api/types";
import { analysisError, useAnalysis } from "./AnalysisProvider";
import { Button, IconButton } from "./Chrome";
import styles from "./workspace-ai-permission.module.css";

export function WorkspaceAiPermission() {
  const { setConsent } = useAnalysis();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ConsentState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal(); title.current?.focus();
    let current = true;
    assistant.consent("workspace").then(value => { if (current) setState(value); }, failure => { if (current) setError(analysisError(failure)); });
    return () => { current = false; };
  }, [open]);
  function close() {
    setOpen(false);
    requestAnimationFrame(() => opener.current?.querySelector("button")?.focus());
  }
  async function save() {
    if (!state) return;
    setBusy(true); setError("");
    try { const saved = await setConsent(!state.allowed, true); if (saved) setState(saved); }
    catch (failure) { setError(analysisError(failure)); }
    finally { setBusy(false); }
  }
  return <>
    <span ref={opener}><IconButton label="AI settings" className="theme-toggle icon-button" onClick={() => { setState(null); setError(""); setOpen(true); }} aria-haspopup="dialog"><Cpu size={17} aria-hidden="true" /></IconButton></span>
    {open && <dialog ref={dialog} className={styles.dialog} aria-labelledby="workspace-ai-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) close(); }}>
      <header><h2 id="workspace-ai-title" tabIndex={-1} ref={title}>Workspace AI</h2><IconButton label="Close AI settings" onClick={close}><X size={17} aria-hidden="true" /></IconButton></header>
      <p>One permission for all existing and future experiments in this local workspace.</p>
      {state ? <>
        <p role="status">{state.allowed ? "AI is enabled. New analyses run automatically; saved answers are reused." : "AI is off. Recorded evidence remains available."}</p>
        <details><summary>What AI receives</summary><p>{state.disclosure}</p></details>
        {state.allowed && <p className="note">Turning AI off cancels active analyses and removes cloud-derived answers and briefs. Evidence-only drafts are retained.</p>}
        <Button variant={state.allowed ? "secondary" : "primary"} loading={busy} onClick={() => void save()}>{state.allowed ? "Turn off AI analysis" : "Enable AI analysis"}</Button>
      </> : !error && <p role="status">Checking AI permission…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!state && error && <Button variant="secondary" onClick={() => { setError(""); void assistant.consent("workspace").then(setState, failure => setError(analysisError(failure))); }}>Retry</Button>}
    </dialog>}
  </>;
}
