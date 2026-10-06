import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { StateBlock } from "./Chrome";
import { ArrowRight, ChevronRight, Cpu } from "lucide-react";
import { candidateLabel } from "../format";
import type { CandidateKind } from "../api/types";

const SHORT_QUESTIONS = ["Pass or fail?", "Weakest fault", "Did fault training help?", "What next?"];

export function EvidenceGuide({ collapsed = false }: { collapsed?: boolean }) {
  const api = useEvidence();
  const result = useApi(() => api.decision(), [api]);
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => { setSelected(null); }, [api]);
  const answer = selected == null ? null : result.data?.guide[selected];
  const sentences = answer?.answer.split(/(?<=[.!?])\s+(?=[A-Z])/);
  const summary = selected === 0 ? result.data?.title : sentences?.slice(0, 2).join(" ");
  const detail = selected === 0 ? answer?.answer : sentences?.slice(2).join(" ");
  const inspected = result.data?.inspected_candidate?.split("/");
  const ref = useRef<HTMLElement>(null);
  useEffect(() => { if (ref.current) ref.current.inert = collapsed; }, [collapsed]);
  return (
    <aside ref={ref} id="evidence-guide" className="evidence-guide" aria-labelledby="guide-heading" tabIndex={-1}>
      <div className="guide-inner">
        <header className="guide-head">
          <h2 id="guide-heading">Evidence guide</h2>
        </header>
        <div className="guide-content">
          <StateBlock loading={result.loading} error={result.error} empty={!result.loading && !result.data?.guide.length}>
            {inspected && (
              <div className="guide-context">
                <span className="guide-avatar" aria-hidden="true"><Cpu size={15} strokeWidth={1.9} /></span>
                <span><strong>{candidateLabel(inspected[0] as CandidateKind, inspected[1])}</strong>{result.data?.partition === "holdout" ? "Final validation" : "Development evidence"}</span>
              </div>
            )}
            <div className="guide-questions" role="list" aria-label="Evidence topics">
              {result.data?.guide.map((item, i) => {
                const open = selected === i && answer;
                return (
                  <div className="guide-item" role="listitem" key={item.question}>
                    <button
                      type="button"
                      className="guide-question"
                      aria-label={item.question}
                      aria-pressed={selected === i}
                      aria-expanded={selected === i}
                      aria-controls={selected === i ? "guide-answer" : undefined}
                      onClick={() => setSelected(i)}
                    >
                      <span className="guide-question-label">{SHORT_QUESTIONS[i] ?? item.question}</span>
                      <ChevronRight size={15} aria-hidden="true" />
                    </button>
                    {open && (
                      <section id="guide-answer" className="guide-answer" aria-live="polite" aria-atomic="true">
                        <div className="guide-answer-card" key={`${result.data?.inspected_candidate}/${selected}`}>
                          <p>{summary}</p>
                          {detail && <details><summary>Full explanation</summary><p>{detail}</p></details>}
                          <Link className="guide-evidence-link" to={answer.link}>{answer.link_label}<ArrowRight size={14} aria-hidden="true" /></Link>
                        </div>
                      </section>
                    )}
                  </div>
                );
              })}
            </div>
            {selected == null && <section id="guide-answer" className="guide-answer" aria-live="polite" aria-atomic="true" />}
          </StateBlock>
        </div>
      </div>
    </aside>
  );
}
