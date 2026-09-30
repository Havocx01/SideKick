import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { StateBlock } from "./Chrome";
import { ArrowRight, BookOpen } from "lucide-react";

export function EvidenceGuide() {
  const api = useEvidence();
  const result = useApi(() => api.decision(), [api]);
  const [selected, setSelected] = useState<number | null>(null);
  const answer = selected === null ? null : result.data?.guide[selected];
  return (
    <aside id="evidence-guide" className="evidence-guide" aria-labelledby="guide-heading" tabIndex={-1}>
      <div className="guide-head">
        <BookOpen size={18} strokeWidth={1.75} aria-hidden="true" />
        <h2 id="guide-heading">Evidence guide</h2>
      </div>
      <p className="guide-description">Understand this experiment’s recommendation. Answers stay tied to its recorded metrics, even when you inspect another candidate.</p>
      <StateBlock loading={result.loading} error={result.error}>
        <div className="guide-questions">
          {result.data?.guide.map((item, i) => (
            <button className="guide-question" aria-pressed={selected === i} aria-controls="guide-answer" key={item.question} onClick={() => setSelected(i)}>
              <span>{item.question}</span><ArrowRight size={16} aria-hidden="true" />
            </button>
          ))}
        </div>
        <div id="guide-answer" className="guide-answer" aria-live="polite" aria-atomic="true">
          {answer && (
            <>
              <h3>{answer.question}</h3>
              <p>{answer.answer}</p>
              <Link to={answer.link}>{answer.link_label} <ArrowRight size={16} aria-hidden="true" /></Link>
            </>
          )}
        </div>
        {!answer && <p className="guide-placeholder">Choose a question to see the supporting result and where to inspect it.</p>}
      </StateBlock>
      <p className="guide-foot">Metric-based answers. No external model calls or API key.</p>
    </aside>
  );
}
