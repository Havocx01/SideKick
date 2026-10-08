import { useEffect, useId, useState } from "react";
import { Check, ChevronDown, CircleAlert, Database } from "lucide-react";
import type { AnalysisStage, EvidenceReference } from "../api/types";

/* Adapted from Beautiful UI's ThinkingState, ContextCards and StreamingText.
 * https://github.com/slev12397/beautiful-ui/tree/main/components/primitives
 * MIT, Copyright (c) 2026 Shane Levine. See BEAUTIFUL-UI-LICENSE.
 * Sidekick supplies the theme, real task states and verified measurements.
 * The answer reveal starts after verification; it is not a provider token stream.
 * Gallery loops and sample data are omitted.
 */

/** Expands while the job runs, then settles into a collapsed, reopenable trace. */
export function AssistantThinkingState({ stages, working, label, doneLabel }: { stages: AnalysisStage[]; working: boolean; label: string; doneLabel: string }) {
  const [manual, setManual] = useState<boolean | null>(null);
  const expanded = manual ?? working;
  const traceId = useId();
  const visible = stages.filter(stage => stage.status !== "pending");
  return <section className="assistant-thinking" data-working={working} aria-label={working ? "Analysis progress" : "Analysis trace"} aria-busy={working}>
    <button type="button" className="assistant-thinking-toggle" aria-label={working ? label : doneLabel} aria-expanded={expanded} aria-controls={traceId} disabled={!working && !visible.length} onClick={() => setManual(!expanded)}>
      <svg className="assistant-thinking-glyph" width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" /></svg>
      <span role="status" className="assistant-thinking-status">{working
        ? <span key="working" className="assistant-thinking-label">{label}</span>
        : <span key="done" className="assistant-thinking-done">{doneLabel}</span>}</span>
      {visible.length > 0 && <ChevronDown size={14} className="assistant-thinking-chevron" aria-hidden="true" />}
    </button>
    <div className="assistant-thinking-panel" data-expanded={expanded}>
      <div className="assistant-thinking-clip">
        <div id={traceId} className="assistant-thinking-trace">
          <ol aria-label="Analysis steps">
            {visible.map(stage => <li key={stage.id} className={`assistant-thinking-step ${stage.status}`} aria-current={stage.status === "running" ? "step" : undefined}>
              <span key={stage.status} className="assistant-thinking-icon" aria-hidden="true">{stage.status === "completed" ? <Check size={13} strokeWidth={2.4} /> : stage.status === "failed" ? <CircleAlert size={13} /> : <span className="assistant-thinking-spinner" />}</span>
              <span>{stage.label}<span className="sr-only">: {stage.status}</span></span>
            </li>)}
          </ol>
        </div>
      </div>
    </div>
  </section>;
}

const WORD_MS = 38;

export function streamWords(text: string) {
  return text.match(/\S+\s*/g) ?? [];
}

/** `delay` lets the thinking trace finish collapsing before the answer starts.
 * Reduced motion keeps the word pacing; CSS drops the blur and movement. */
export function useStreamingReveal(wordCount: number, delay = 0, immediate = false) {
  const [visible, setVisible] = useState(0);
  useEffect(() => {
    if (immediate) { setVisible(wordCount); return; }
    setVisible(0);
    if (wordCount === 0) return;
    let count = 0;
    let timer: number | undefined;
    const start = window.setTimeout(() => {
      timer = window.setInterval(() => {
        count += 1;
        setVisible(count);
        if (count >= wordCount) window.clearInterval(timer);
      }, WORD_MS);
    }, delay);
    return () => { window.clearTimeout(start); window.clearInterval(timer); };
  }, [wordCount, delay, immediate]);
  return immediate ? wordCount : Math.min(visible, wordCount);
}

/** Beautiful UI's word reveal with stable wrapping and an accessible full answer. */
export function StreamingText({ text, visibleWords, caret = false }: { text: string; visibleWords: number; caret?: boolean }) {
  const words = streamWords(text);
  const count = Math.max(0, Math.min(visibleWords, words.length));
  return <>
    <span className="sr-only assistant-stream-accessible">{text}</span>
    <span aria-hidden="true">{words.map((word, index) => {
      const trimmed = word.trimEnd();
      return <span className="assistant-stream-word" data-revealed={index < count} key={index}>
        {trimmed}{caret && index === count - 1 && count < words.length && <span className="assistant-stream-caret" />}{word.slice(trimmed.length)}
      </span>;
    })}</span>
  </>;
}

export function EvidenceCitation({ number, expanded, controls, onClick, disabled = false }: {
  number: number;
  expanded: boolean;
  controls: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return <button type="button" className="assistant-citation" aria-label={`Show evidence for finding ${number}`} aria-expanded={expanded} aria-controls={controls} disabled={disabled} onClick={onClick}>
    <Database size={12} aria-hidden="true" /><span>{number}</span>
  </button>;
}

export function EvidenceContextCards({ sources, variant = "cards" }: { sources: EvidenceReference[]; variant?: "cards" | "rows" }) {
  const groups = new Map<string, EvidenceReference[]>();
  for (const source of sources) {
    const context = source.context || "Evidence";
    const group = groups.get(context) ?? [];
    group.push(source);
    groups.set(context, group);
  }
  return <div className={variant === "rows" ? "assistant-context-rows" : "assistant-context-cards"}>
    {[...groups].map(([context, measurements]) => {
      const parts = context.split(" · ");
      const hasDetail = parts.length > 2;
      return <div className="assistant-context-card" key={context}>
      <div className="assistant-context-heading">{variant === "rows" ? <div><strong>{hasDetail ? parts.slice(2).join(" · ") : context}</strong>{hasDetail && <small>{parts.slice(0, 2).join(" · ")}</small>}</div> : <><Database size={14} aria-hidden="true" /><span>{context}</span></>}</div>
      <dl>{measurements.map(source => <div className="assistant-context-measure" key={source.id}><dt>{source.label}</dt><dd>{source.display}</dd></div>)}</dl>
    </div>; })}
  </div>;
}
