import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { CopilotAnswer } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Badge } from "./Chrome";
import { Prose } from "./Prose";

interface Exchange {
  question: string;
  answer?: CopilotAnswer;
  error?: string;
  pending?: boolean;
}

/**
 * The copilot, with its working shown.
 *
 * Every answer displays which tools it called and whether each figure matched a
 * recorded metric. That transparency is the point: an assistant that states
 * numbers about a safety decision should be auditable, and the reviewer should not
 * have to take the claim of verification on trust.
 */
export function CopilotPanel({ onClose }: { onClose: () => void }) {
  const status = useApi(() => api.copilotStatus(), []);
  const suggestions = useApi(() => api.copilotSuggestions(), []);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [exchanges]);

  async function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setDraft("");
    setBusy(true);
    setExchanges((current) => [...current, { question: trimmed, pending: true }]);

    try {
      const answer = await api.askCopilot(trimmed);
      setExchanges((current) =>
        current.map((exchange, index) =>
          index === current.length - 1 ? { question: trimmed, answer } : exchange,
        ),
      );
    } catch (cause) {
      setExchanges((current) =>
        current.map((exchange, index) =>
          index === current.length - 1
            ? { question: trimmed, error: (cause as Error).message }
            : exchange,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="copilot" aria-label="Copilot">
      <header className="copilot-head">
        <div>
          <h2>Copilot</h2>
          <p className="note" style={{ margin: "2px 0 0" }}>
            {status.data?.note ?? "Checking availability…"}
          </p>
        </div>
        <button onClick={onClose} aria-label="Close copilot">
          Close
        </button>
      </header>

      <div className="copilot-log" ref={logRef}>
        {exchanges.length === 0 ? (
          <div>
            <p className="note">
              Ask about the recorded evaluation. The copilot looks results up through a fixed set
              of tools and never produces a prediction of its own.
            </p>
            <div className="pill-row" style={{ marginTop: 10 }}>
              {(suggestions.data?.suggestions ?? []).map((suggestion) => (
                <button key={suggestion} onClick={() => submit(suggestion)} disabled={busy}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {exchanges.map((exchange, index) => (
          <div key={index} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="bubble question">{exchange.question}</div>
            {exchange.pending ? <div className="bubble answer note">Looking it up…</div> : null}
            {exchange.error ? <div className="bubble error">{exchange.error}</div> : null}
            {exchange.answer ? <AnswerBubble answer={exchange.answer} /> : null}
          </div>
        ))}
      </div>

      <div className="copilot-foot">
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit(draft);
          }}
          placeholder="Which model should we deploy, and why?"
          aria-label="Question"
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="note">Ctrl or Cmd + Enter to send</span>
          <button className="primary" onClick={() => submit(draft)} disabled={busy || !draft.trim()}>
            {busy ? "Working…" : "Ask"}
          </button>
        </div>
      </div>
    </aside>
  );
}

function AnswerBubble({ answer }: { answer: CopilotAnswer }) {
  const claims = answer.claims ?? [];
  const verified = claims.filter((claim) => claim.verified).length;
  const toolCalls = answer.tool_calls ?? [];
  const unverified = answer.unverified_claims ?? 0;

  return (
    <div className="bubble answer">
      <Prose text={answer.text} />

      <div className="answer-meta">
        <div className="tool-trace">
          {toolCalls.map((call, index) => (
            <span key={index} className={call.ok ? "tool-chip" : "tool-chip failed"}>
              {call.name}
              {call.ok ? "" : " failed"}
            </span>
          ))}
          {toolCalls.length === 0 ? <span className="note">no tool was called</span> : null}
        </div>

        <div className="pill-row">
          {claims.length > 0 ? (
            unverified > 0 ? (
              <Badge tone="bad">
                {unverified} of {claims.length} figures unverified
              </Badge>
            ) : (
              <Badge tone="ok">
                {verified} figure{verified === 1 ? "" : "s"} checked against recorded metrics
              </Badge>
            )
          ) : null}
          {answer.degraded ? <Badge tone="info">answered from evidence</Badge> : null}
          {answer.truncated ? <Badge tone="warn">tool budget reached</Badge> : null}
        </div>

        {(answer.citations ?? []).length > 0 ? (
          <div className="note">
            Runs cited: <span className="mono">{(answer.citations ?? []).join(", ")}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
