import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { StateBlock } from "./Chrome";

export function EvidenceGuide() {
  const api = useEvidence();
  const result = useApi(() => api.decision(), [api]);
  const [selected, setSelected] = useState<number | null>(null);
  const answer = selected === null ? null : result.data?.guide[selected];
  return (
    <aside id="evidence-guide" className="evidence-guide" aria-labelledby="guide-heading" tabIndex={-1}>
      <div className="guide-head">
        <h2 id="guide-heading">Evidence guide</h2>
      </div>
      <p className="note">Answers come directly from this result’s recorded metrics. No external model is used.</p>
      <StateBlock loading={result.loading} error={result.error}>
        <div className="guide-questions">
          {result.data?.guide.map((item, i) => (
            <button aria-pressed={selected === i} key={item.question} onClick={() => setSelected(i)}>
              {item.question}
            </button>
          ))}
        </div>
        <div className="guide-answer" aria-live="polite">
          {answer && (
            <>
              <h3>{answer.question}</h3>
              <p>{answer.answer}</p>
              <Link to={answer.link}>{answer.link_label}</Link>
            </>
          )}
        </div>
      </StateBlock>
    </aside>
  );
}
