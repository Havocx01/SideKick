import { useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { Check, RotateCcw, X } from "lucide-react";
import styles from "./experiment-library.module.css";

export function InlineLibraryName({ name, maxLength, label, inputRef, save, done }: {
  name: string; maxLength: number; label: string; inputRef: RefObject<HTMLInputElement>;
  save: (name: string) => Promise<void>; done: (focus: boolean) => void;
}) {
  const [draft, setDraft] = useState(name);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const finished = useRef(false);
  const saving = useRef(false);
  const attempted = useRef<string | null>(null);
  const errorId = useId();
  useLayoutEffect(() => { inputRef.current?.focus(); inputRef.current?.select(); }, [inputRef]);
  function cancel(focus: boolean) {
    if (saving.current) return;
    finished.current = true;
    done(focus);
  }
  async function commit(explicit: boolean) {
    if (finished.current || saving.current || (!explicit && attempted.current === draft)) return;
    if (draft.trim() === name && name) { finished.current = true; done(explicit); return; }
    attempted.current = draft;
    if (!draft.trim()) { setError("Enter a name."); return; }
    saving.current = true; setPending(true); setError("");
    try {
      await save(draft.trim());
      finished.current = true;
      done(explicit);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save. Try again."); }
    finally { saving.current = false; setPending(false); }
  }
  return <div className={styles.inlineName} data-library-edit onClick={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()}>
    <div className={styles.inlineNameControls}>
      <input ref={inputRef} aria-label={label} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined}
        maxLength={maxLength} value={draft} disabled={pending} onChange={event => { setDraft(event.target.value); setError(""); }}
        onKeyDown={event => { event.stopPropagation(); if (event.key === "Escape") { event.preventDefault(); cancel(true); } else if (event.key === "Enter") { event.preventDefault(); void commit(true); } }}
        onBlur={event => {
          if (event.currentTarget.parentElement?.parentElement?.contains(event.relatedTarget as Node | null)) return;
          if ((event.relatedTarget as HTMLElement | null)?.closest("[data-library-nav],a[href]")) cancel(false);
          else void commit(false);
        }} />
      <button type="button" className={styles.nameAction} aria-label={error ? "Retry saving name" : "Save name"} disabled={pending} onClick={() => { void commit(true); }}>{error ? <RotateCcw size={14} aria-hidden="true" /> : <Check size={14} aria-hidden="true" />}</button>
      <button type="button" className={styles.nameAction} aria-label="Cancel rename" disabled={pending} onClick={() => cancel(true)}><X size={14} aria-hidden="true" /></button>
    </div>
    {error && <p id={errorId} className={styles.nameError} role="alert">{error}</p>}
    {pending && <span className="sr-only" role="status">Saving name…</span>}
  </div>;
}
