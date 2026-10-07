import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { assistant } from "../api/assistant";
import { ApiError } from "../api/client";
import type { AnalysisRecord, AnalysisRequest, AssistantCapabilities, ConsentState } from "../api/types";

export function analysisError(error: unknown) {
  return error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Analysis unavailable. Try again.";
}
const isActive = (record?: AnalysisRecord | null) => record?.status === "running" || record?.status === "queued";
interface AnalysisState {
  open: boolean;
  context: AnalysisRequest | null;
  record: AnalysisRecord | null;
  capabilities: AssistantCapabilities | null;
  consent: ConsentState | null;
  error: string;
  pending: boolean;
  start: (context: AnalysisRequest) => void;
  retry: () => void;
  close: (restoreFocus?: boolean) => void;
  cancel: () => Promise<void>;
  setConsent: (allowed: boolean) => Promise<void>;
  unlock: (code: string) => Promise<void>;
  saveBrief: (text: string) => Promise<void>;
  enabled: (task: AnalysisRequest["task"]) => boolean;
}
const AnalysisContext = createContext<AnalysisState | null>(null);
export function useAnalysis() {
  const value = useContext(AnalysisContext);
  if (!value) throw new Error("AnalysisProvider is missing.");
  return value;
}

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [context, setContext] = useState<AnalysisRequest | null>(null);
  const [record, setRecord] = useState<AnalysisRecord | null>(null);
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [consent, updateConsent] = useState<ConsentState | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [tasks, setTasks] = useState<string[]>([]);
  const generation = useRef(0);
  useEffect(() => {
    let live = true;
    assistant.capabilities().then(caps => { if (live) setTasks(caps.tasks); }, () => { if (live) setTasks([]); });
    return () => { live = false; };
  }, []);
  const recordRef = useRef<AnalysisRecord | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const updateRecord = (value: AnalysisRecord | null) => { recordRef.current = value; setRecord(value); };
  const close = useCallback((restoreFocus = true) => {
    generation.current += 1;
    const previous = recordRef.current;
    if (previous && isActive(previous)) void assistant.cancel(previous.id).catch(() => undefined);
    setOpen(false); setPending(false); updateRecord(null); setContext(null); setError("");
    if (restoreFocus) requestAnimationFrame(() => { if (opener.current?.isConnected) opener.current.focus(); });
  }, []);
  // A replay cycle is captured by the action. Playback does not invalidate it.
  const params = new URLSearchParams(location.search);
  const scope = [location.pathname, ...["candidate", "partition", "equipment", "scenario", "step"].map(key => params.get(key))].join("|");
  useEffect(() => { close(false); }, [scope, close]);
  useEffect(() => () => { generation.current += 1; const current = recordRef.current; if (current && isActive(current)) void assistant.cancel(current.id).catch(() => undefined); }, []);

  async function run(next: AnalysisRequest, rememberOpener: boolean) {
    const token = ++generation.current;
    const previous = recordRef.current;
    if (previous && isActive(previous)) void assistant.cancel(previous.id).catch(() => undefined);
    if (rememberOpener) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setContext(next); setOpen(true); setError(""); setPending(true); updateRecord(null); setCapabilities(null); updateConsent(null);
    try {
      const caps = await assistant.capabilities(next.experiment_id);
      if (token !== generation.current) return;
      setCapabilities(caps);
      if (caps.consent_required && next.experiment_id) {
        const state = await assistant.consent(next.experiment_id);
        if (token !== generation.current) return;
        updateConsent(state);
      }
      const started = await assistant.start(next);
      if (token !== generation.current) { if (isActive(started)) void assistant.cancel(started.id).catch(() => undefined); return; }
      updateRecord(started);
    } catch (failure) { if (token === generation.current) setError(analysisError(failure)); }
    finally { if (token === generation.current) setPending(false); }
  }
  useEffect(() => {
    if (!record || !isActive(record)) return;
    const token = generation.current;
    const timer = window.setTimeout(async () => {
      try { const next = await assistant.get(record.id); if (token === generation.current) updateRecord(next); }
      catch (failure) { if (token === generation.current) { setError(analysisError(failure)); } }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [record]);

  async function cancel() {
    const current = recordRef.current;
    if (!current) { close(); return; }
    const token = ++generation.current;
    try { const next = await assistant.cancel(current.id); if (token === generation.current) updateRecord(next); }
    catch (failure) { if (token === generation.current) setError(analysisError(failure)); }
  }
  async function setConsent(allowed: boolean) {
    if (!context?.experiment_id) return;
    const token = ++generation.current;
    const current = recordRef.current;
    if (current && isActive(current)) await assistant.cancel(current.id);
    const state = await assistant.setConsent(context.experiment_id, allowed);
    if (token !== generation.current) return;
    updateConsent(state);
    updateRecord(null);
    const caps = await assistant.capabilities(context.experiment_id);
    if (token === generation.current) setCapabilities(caps);
  }
  async function unlock(code: string) {
    const token = generation.current;
    await assistant.unlock(code);
    const caps = await assistant.capabilities(context?.experiment_id);
    if (token === generation.current) setCapabilities(caps);
  }
  async function saveBrief(text: string) {
    const current = recordRef.current;
    if (!current) return;
    const token = generation.current;
    const next = await assistant.saveBrief(current.id, text);
    if (token === generation.current) updateRecord(next);
  }
  return <AnalysisContext.Provider value={{ open, context, record, capabilities, consent, error, pending, start: next => void run(next, true), retry: () => { if (context) void run(context, false); }, close, cancel, setConsent, unlock, saveBrief, enabled: task => tasks.includes(task) }}>{children}</AnalysisContext.Provider>;
}
