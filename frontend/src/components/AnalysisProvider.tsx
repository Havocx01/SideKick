import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { assistant } from "../api/assistant";
import { ApiError } from "../api/client";
import type { AnalysisRecord, AnalysisRequest, AssistantCapabilities, ColumnMapping, ConsentState } from "../api/types";

export function analysisError(error: unknown) {
  return error instanceof ApiError ? error.detail || error.message : error instanceof Error ? error.message : "Analysis unavailable. Try again.";
}
const isActive = (record?: AnalysisRecord | null) => record?.status === "running" || record?.status === "queued";
// Match the server's analysis/brief equivalence without sorting candidate order.
export function analysisContextKey(value: AnalysisRequest) {
  const mapping = value.mapping ? Object.fromEntries(Object.entries(value.mapping).sort(([a], [b]) => a.localeCompare(b))) : null;
  return JSON.stringify({ task: value.task === "brief" ? (value.candidates?.length === 2 ? "compare" : value.equipment_id && value.scenario_id ? "warning" : "investigate") : value.task,
    experiment_id: value.experiment_id ?? null, dataset_id: value.dataset_id ?? null, mapping,
    complete_histories: value.complete_histories ?? false, candidates: value.candidates ?? [], partition: value.partition ?? "out_of_fold",
    scenario_id: value.scenario_id ?? null, equipment_id: value.equipment_id ?? null, cycle: value.cycle ?? null });
}
type VisibleRecord = AnalysisRecord & { output_currency?: "current" | "historical" };
interface AnalysisState {
  open: boolean;
  context: AnalysisRequest | null;
  record: VisibleRecord | null;
  capabilities: AssistantCapabilities | null;
  consent: ConsentState | null;
  error: string;
  pending: boolean;
  verifying: boolean;
  canRetry: boolean;
  start: (context: AnalysisRequest, applyMapping?: (mapping: ColumnMapping) => void) => void;
  applyMapping: () => void;
  prepareReview: () => Promise<void>;
  retry: () => void;
  refreshStatus: () => void;
  statusRecovery: "" | "refresh" | "unavailable";
  close: (restoreFocus?: boolean) => void;
  cancel: () => Promise<void>;
  setConsent: (allowed: boolean) => Promise<void>;
  unlock: (code: string) => Promise<void>;
  saveBrief: (text: string) => Promise<void>;
  editBrief: (text: string) => void;
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
  const [record, setRecord] = useState<VisibleRecord | null>(null);
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [consent, updateConsent] = useState<ConsentState | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [statusRecovery, setStatusRecovery] = useState<"" | "refresh" | "unavailable">("");
  const [pollVersion, setPollVersion] = useState(0);
  const [tasks, setTasks] = useState<string[]>([]);
  const generation = useRef(0);
  const cancelledAdmissions = useRef(new Set<number>());
  useEffect(() => {
    let live = true;
    assistant.capabilities().then(caps => { if (live) setTasks(caps.tasks); }, () => { if (live) setTasks([]); });
    return () => { live = false; };
  }, []);
  const recordRef = useRef<VisibleRecord | null>(null);
  const contextRef = useRef<AnalysisRequest | null>(null);
  const requestRef = useRef<{ key: string; promise: Promise<void> } | null>(null);
  const revisions = useRef(new Map<string, number>());
  const draftErrors = useRef(new Map<string, string>());
  const conversions = useRef(new Map<string, Promise<AnalysisRecord>>());
  const opener = useRef<HTMLElement | null>(null);
  const mappingReceiver = useRef<((mapping: ColumnMapping) => void) | undefined>(undefined);
  const draft = useRef<{ id: string; text: string; revision: number } | null>(null);
  const draftTimer = useRef<number | undefined>();
  const writes = useRef(new Map<string, Promise<AnalysisRecord>>());
  const updateRecord = (value: VisibleRecord | null) => { recordRef.current = value; setRecord(value); };
  const writeBrief = useCallback((id: string, text: string, draftOnly: boolean, revision: number) => {
    // Serialize writes so a delayed autosave cannot overwrite a later edit or explicit save.
    const previous = writes.current.get(id)?.catch(() => undefined) ?? Promise.resolve();
    const write = previous.then(() => assistant.saveBrief(id, text, draftOnly));
    writes.current.set(id, write);
    void write.then(saved => {
      const current = recordRef.current;
      if (current?.id === id && (revisions.current.get(id) ?? 0) === revision && (current.brief_text ?? current.result?.brief_draft ?? "") === text) {
        draftErrors.current.delete(id); setError("");
        updateRecord({ ...current, brief_text: saved.brief_text, brief_saved_at: saved.brief_saved_at, updated_at: saved.updated_at });
      }
    }).catch(failure => {
      if (recordRef.current?.id === id && (revisions.current.get(id) ?? 0) === revision) {
        const message = `Draft could not be saved. ${analysisError(failure)}`;
        draftErrors.current.set(id, message); setError(message);
      }
    }).finally(() => { if (writes.current.get(id) === write) writes.current.delete(id); });
    return write;
  }, []);
  const convertBrief = useCallback((id: string) => {
    const existing = conversions.current.get(id);
    if (existing) return existing;
    // Conversion and draft writes share a queue. A conversion response can
    // never arrive after a newer explicit Save acknowledgement.
    const previous = writes.current.get(id)?.catch(() => undefined) ?? Promise.resolve();
    const conversion = previous.then(() => assistant.prepareReview(id));
    conversions.current.set(id, conversion);
    writes.current.set(id, conversion);
    void conversion.finally(() => {
      if (conversions.current.get(id) === conversion) conversions.current.delete(id);
      if (writes.current.get(id) === conversion) writes.current.delete(id);
    }).catch(() => undefined);
    return conversion;
  }, []);
  const flushDraft = useCallback(() => {
    window.clearTimeout(draftTimer.current);
    const current = draft.current;
    draft.current = null;
    return current ? writeBrief(current.id, current.text, true, current.revision) : undefined;
  }, [writeBrief]);
  const close = useCallback((restoreFocus = true) => {
    void flushDraft();
    // Closing hides the saved job; only the explicit Cancel action stops provider work.
    setOpen(false);
    mappingReceiver.current = undefined;
    if (restoreFocus) requestAnimationFrame(() => { if (opener.current?.isConnected) opener.current.focus(); });
  }, [flushDraft]);
  useEffect(() => {
    const saveOnLeave = () => { void flushDraft(); };
    window.addEventListener("pagehide", saveOnLeave);
    return () => window.removeEventListener("pagehide", saveOnLeave);
  }, [flushDraft]);
  // A replay cycle is captured by the action. Playback does not invalidate it.
  const params = new URLSearchParams(location.search);
  const scope = [location.pathname, ...["candidate", "partition", "equipment", "scenario", "step", "dataset"].map(key => params.get(key))].join("|");
  useEffect(() => { close(false); }, [scope, close]);
  useEffect(() => () => { void flushDraft(); generation.current += 1; }, [flushDraft]);

  function run(next: AnalysisRequest, rememberOpener: boolean, force = false) {
    void flushDraft();
    const previous = recordRef.current;
    const key = analysisContextKey(next);
    const same = Boolean(contextRef.current && analysisContextKey(contextRef.current) === key);
    if (rememberOpener) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    contextRef.current = next; setContext(next); setOpen(true);
    // Visibility changes join a pending admission or verification instead of replacing it.
    if (!force && same && requestRef.current?.key === key) return requestRef.current.promise;
    if (requestRef.current) cancelledAdmissions.current.add(generation.current);
    const token = ++generation.current;
    const revalidate = !force && same && Boolean(previous);
    const failedReopen = !force && same && !previous && Boolean(error);
    const retainedError = error;
    if (!revalidate && previous && isActive(previous)) void assistant.cancel(previous.id).catch(() => undefined);
    setError(""); setStatusRecovery(""); setPending(!revalidate && !failedReopen); setVerifying(revalidate || failedReopen); setCapabilities(null); updateConsent(null);
    if (!revalidate) updateRecord(null);
    const promise = (async () => {
      try {
        await Promise.all([...writes.current.values()].map(write => write.catch(() => undefined)));
        const caps = await assistant.capabilities(next.experiment_id, next.dataset_id);
        if (token !== generation.current) return;
        setCapabilities(caps);
        const consentScope = next.dataset_id ? `dataset:${next.dataset_id}` : next.experiment_id;
        let consentPermitsDraft = true;
        if (caps.consent_required && consentScope) {
          const state = await assistant.consent(consentScope);
          if (token !== generation.current) return;
          updateConsent(state);
          consentPermitsDraft = state.allowed;
        }
        if (failedReopen) { setError(retainedError); return; }
        // A failed admission response has no known job ID. Explicit recovery
        // uses reuse so a server-admitted job cannot become a second paid job.
        let started: VisibleRecord = revalidate && previous ? await assistant.get(previous.id) : await assistant.start(next, !force || !previous);
        if (token !== generation.current) {
          // A deliberate context replacement may arrive before its admitted ID does.
          if (!revalidate && cancelledAdmissions.current.has(token) && isActive(started)) void assistant.cancel(started.id).catch(() => undefined);
          cancelledAdmissions.current.delete(token);
          return;
        }
        // A fresh browser may also receive a historical saved record via reuse.
        // Its response-only currency and current access come from a GET.
        if (!revalidate && started.reused && started.status === "completed") {
          started = await assistant.get(started.id);
          if (token !== generation.current) return;
          started = { ...started, reused: true };
        }
        const local = recordRef.current;
        // Verify access first. Only retain unsaved edits when the same permitted
        // result remains available; revoked cloud output can never restore a draft.
        const retainDraft = revalidate && local?.id === started.id && local.brief_text !== null && !local.brief_saved_at && revisions.current.has(local.id)
          && !started.error && (consentPermitsDraft || started.brief_text !== null) && Boolean(started.result) && local.result?.mode === started.result?.mode && local.result?.evidence_digest === started.result?.evidence_digest;
        updateRecord(revalidate ? { ...started, reused: true, ...(retainDraft ? { brief_text: local!.brief_text, brief_saved_at: null } : {}) } : started);
        if (retainDraft) setError(draftErrors.current.get(started.id) ?? "");
      } catch (failure) {
        if (token === generation.current) {
          if (revalidate) { updateRecord(null); setStatusRecovery("unavailable"); }
          setError(analysisError(failure));
        }
      } finally {
        cancelledAdmissions.current.delete(token);
        if (token === generation.current) { setPending(false); setVerifying(false); }
      }
    })();
    requestRef.current = { key, promise };
    void promise.finally(() => { if (requestRef.current?.promise === promise) requestRef.current = null; });
    return promise;
  }
  useEffect(() => {
    if (!open || pending || verifying || !record || !isActive(record)) return;
    const token = generation.current;
    const id = record.id;
    let stopped = false;
    let failures = 0;
    let timer: number;
    const current = () => !stopped && token === generation.current && recordRef.current?.id === id;
    const schedule = (delay: number) => { timer = window.setTimeout(read, delay); };
    async function read() {
      try {
        const next = await assistant.get(id);
        if (!current()) return;
        failures = 0; setError(""); setStatusRecovery(""); updateRecord(next);
        if (isActive(next)) schedule(700);
      } catch (failure) {
        if (!current()) return;
        if (failure instanceof ApiError && (failure.status === 403 || failure.status === 404)) {
          updateRecord(null); setStatusRecovery("unavailable"); setError(analysisError(failure));
          if (contextRef.current) {
            try { const caps = await assistant.capabilities(contextRef.current.experiment_id, contextRef.current.dataset_id); if (token === generation.current) setCapabilities(caps); }
            catch { if (token === generation.current) setCapabilities(null); }
          }
          return;
        }
        failures += 1;
        if (failures >= 5) {
          setStatusRecovery("refresh"); setError("Status could not be refreshed. Your analysis is saved; refresh its status to continue."); return;
        }
        schedule([700, 1500, 3000, 5000][failures - 1] ?? 5000);
      }
    }
    schedule(pollVersion ? 0 : 700);
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [record?.id, record?.status, open, pending, verifying, pollVersion]);

  useEffect(() => {
    if (!open || pending || verifying || context?.task !== "brief" || record?.status !== "completed" || record.context.task === "brief") return;
    const token = generation.current;
    const revision = revisions.current.get(record.id) ?? 0;
    let stopped = false;
    const conversion = convertBrief(record.id);
    conversion.then(next => {
      if (!stopped && token === generation.current) {
        const local = recordRef.current;
        const retainDraft = local?.id === next.id && local.brief_text !== null && (revisions.current.get(local.id) ?? 0) !== revision
          && !next.error && (consent?.allowed !== false || next.brief_text !== null) && local.result?.mode === next.result?.mode && local.result?.evidence_digest === next.result?.evidence_digest;
        updateRecord({ ...next, output_currency: record.output_currency, ...(retainDraft ? { brief_text: local!.brief_text, brief_saved_at: local!.brief_saved_at } : {}) });
      }
    }, failure => { if (!stopped && token === generation.current) setError(analysisError(failure)); });
    return () => { stopped = true; };
  }, [open, pending, verifying, consent?.allowed, context?.task, record?.id, record?.status, record?.context.task, record?.output_currency, convertBrief]);

  async function cancel() {
    const current = recordRef.current;
    if (requestRef.current) cancelledAdmissions.current.add(generation.current);
    if (!current) { generation.current += 1; requestRef.current = null; setPending(false); close(); return; }
    const token = ++generation.current;
    try { const next = await assistant.cancel(current.id); if (token === generation.current) updateRecord(next); }
    catch (failure) { if (token === generation.current) { setError(`Cancellation could not be confirmed. ${analysisError(failure)}`); setStatusRecovery("refresh"); } }
  }
  async function setConsent(allowed: boolean) {
    const consentScope = context?.dataset_id ? `dataset:${context.dataset_id}` : context?.experiment_id;
    if (!context || !consentScope) return;
    if (requestRef.current) cancelledAdmissions.current.add(generation.current);
    const token = ++generation.current;
    window.clearTimeout(draftTimer.current); draft.current = null;
    await Promise.all([...writes.current.values()].map(write => write.catch(() => undefined)));
    const current = recordRef.current;
    if (current && isActive(current)) await assistant.cancel(current.id);
    const state = await assistant.setConsent(consentScope, allowed);
    if (token !== generation.current) return;
    updateConsent(state);
    updateRecord(null);
    const caps = await assistant.capabilities(context.experiment_id, context.dataset_id);
    if (token === generation.current) setCapabilities(caps);
  }
  async function unlock(code: string) {
    const token = generation.current;
    await assistant.unlock(code);
    const caps = await assistant.capabilities(context?.experiment_id, context?.dataset_id);
    if (token === generation.current) setCapabilities(caps);
  }
  async function saveBrief(text: string) {
    const current = recordRef.current;
    if (!current) return;
    window.clearTimeout(draftTimer.current); draft.current = null;
    setError("");
    await writeBrief(current.id, text, false, revisions.current.get(current.id) ?? 0);
  }
  function editBrief(text: string) {
    const current = recordRef.current;
    if (!current || current.status !== "completed" || context?.task !== "brief") return;
    const revision = (revisions.current.get(current.id) ?? 0) + 1;
    revisions.current.set(current.id, revision);
    updateRecord({ ...current, brief_text: text, brief_saved_at: null });
    setError(""); draft.current = { id: current.id, text, revision };
    window.clearTimeout(draftTimer.current);
    draftTimer.current = window.setTimeout(flushDraft, 350);
  }
  async function prepareReview() {
    const current = recordRef.current;
    if (!current || isActive(current)) return;
    const token = ++generation.current;
    await flushDraft();
    await Promise.all([...writes.current.values()]);
    const next = await convertBrief(current.id);
    if (token === generation.current) { contextRef.current = next.context; setContext(next.context); updateRecord({ ...next, output_currency: current.output_currency }); }
  }
  function applyMapping() {
    const mapping = recordRef.current?.result?.suggested_mapping;
    if (!mapping || !mappingReceiver.current || context?.task !== "data") return;
    mappingReceiver.current(mapping); close();
  }
  const canRetry = Boolean(context && capabilities?.tasks.includes(context.task) && !verifying && !pending);
  return <AnalysisContext.Provider value={{ open, context, record, capabilities, consent, error, pending, verifying, canRetry, statusRecovery, refreshStatus: () => { setError(""); setStatusRecovery(""); setPollVersion(version => version + 1); }, start: (next, receiver) => { mappingReceiver.current = receiver; void run(next, true); }, applyMapping, prepareReview, retry: () => { if (contextRef.current) void run(contextRef.current, false, true); }, close, cancel, setConsent, unlock, saveBrief, editBrief, enabled: task => tasks.includes(task) }}>{children}</AnalysisContext.Provider>;
}
