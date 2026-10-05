import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useEvidence } from "../hooks/useEvidence";
import { Button, StateBlock } from "./Chrome";
import { ArrowUpRight, BookOpen, ChevronRight } from "lucide-react";
import { candidateLabel } from "../format";
import type { CandidateKind } from "../api/types";

export function EvidenceGuide() {
  const api = useEvidence();
  const result = useApi(() => api.decision(), [api]);
  const [selected, setSelected] = useState<number | null>(null);
  useEffect(() => { setSelected(null); }, [api]);
  const answer = selected == null ? null : result.data?.guide[selected];
  const sentences = answer?.answer.split(/(?<=[.!?])\s+(?=[A-Z])/);
  const summary = selected === 0 ? result.data?.title : sentences?.slice(0, 2).join(" ");
  const detail = selected === 0 ? answer?.answer : sentences?.slice(2).join(" ");
  return (
    <aside id="evidence-guide" className="evidence-guide" aria-labelledby="guide-heading" tabIndex={-1}>
      <header className="guide-head">
        <BookOpen size={18} strokeWidth={1.75} aria-hidden="true" />
        <h2 id="guide-heading">Evidence guide</h2>
      </header>
      <div className="guide-content">
        <StateBlock loading={result.loading} error={result.error} empty={!result.loading && !result.data?.guide.length}>
          {result.data?.inspected_candidate && <p className="guide-context">{candidateLabel(result.data.inspected_candidate.split("/")[0] as CandidateKind, result.data.inspected_candidate.split("/")[1])}<br />{result.data.partition === "holdout" ? "Final validation" : "Development evidence"}</p>}
          <div className="guide-questions" role="group" aria-label="Evidence topics">
            {result.data?.guide.map((item, i) => (
              <Button variant="ghost" className="guide-question" aria-label={item.question} aria-pressed={selected === i} aria-controls="guide-answer" key={item.question} onClick={() => setSelected(i)}>
                <span className="guide-question-label">{["Pass or fail?", "Weakest fault", "Did fault training help?", "What next?"][i] ?? item.question}</span><ChevronRight size={16} aria-hidden="true" />
              </Button>
            ))}
          </div>
          <section id="guide-answer" className="guide-answer" aria-live="polite" aria-atomic="true">
            {answer && (
              <>
                <h3>{selected != null ? ["Pass or fail?", "Weakest fault", "Did fault training help?", "What next?"][selected] ?? answer.question : answer.question}</h3>
                <p>{summary}</p>
                {detail && <details key={`${result.data?.inspected_candidate}/${selected}`}><summary>Full explanation</summary><p>{detail}</p></details>}
                <Link className="guide-evidence-link" to={answer.link}>{answer.link_label}<ArrowUpRight size={16} aria-hidden="true" /></Link>
              </>
            )}
          </section>
        </StateBlock>
      </div>
    </aside>
  );
}
