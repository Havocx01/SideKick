import type { ReactNode } from "react";
import type { AnalysisResult, DeepReport } from "../api/types";
import { EvidenceContextCards, StreamingText, streamWords, useStreamingReveal } from "./AssistantElements";

/** Qualitative hypotheses stay visibly separate from server-owned observations. */
export function DeepReportView({ result, reused }: { result: AnalysisResult; reused: boolean }) {
  const report = result.deep_report!;
  const firstCheck = report.next_tests[0];
  // Follow the server's test priority without claiming a hypothesis is proven.
  const mainFinding = report.hypotheses.find(item => item.observation_ids.some(id => firstCheck?.observation_ids.includes(id))) ?? report.hypotheses[0];
  const otherFindings = report.hypotheses.filter(item => item !== mainFinding);
  const patterns = report.observations.filter(item => item.kind !== "supporting");
  const supporting = report.observations.filter(item => item.kind === "supporting");
  // A directly cited history belongs beside its explanation. Another example of
  // the same pattern may have a different crossing sequence or warning outcome.
  const recorded = supporting.find(item => item.summary && mainFinding?.observation_ids.includes(item.id))
    ?? supporting.find(item => item.summary && firstCheck?.observation_ids.includes(item.id))
    ?? supporting.find(item => item.summary && item.related_pattern_ids?.some(id => firstCheck?.observation_ids.includes(id)));
  const visible = useStreamingReveal(streamWords(mainFinding?.explanation ?? "").length, 320, reused);
  return <div className="deep-report" aria-label="Deep investigation report">
    {recorded && <section className="deep-recorded-facts" aria-label="Recorded facts">
      <h3>Recorded facts<span>Stored development history</span></h3>
      <p className="note">{recorded.title}</p>
      <p>{recorded.summary}</p>
      <ObservationProof report={report} result={result} ids={[recorded.id]} />
    </section>}
    {mainFinding && <section className="deep-main-finding" aria-label="Possible explanations">
      <h3>Leading hypothesis<span>Possible explanation · Needs checking</span></h3>
      <h4>{mainFinding.title}</h4>
      <p className="deep-summary"><StreamingText text={mainFinding.explanation} visibleWords={visible} /></p>
      <p className="note"><strong>Alternative:</strong> {mainFinding.alternative}</p>
      <ObservationProof report={report} result={result} ids={mainFinding.observation_ids} />
    </section>}
    {!mainFinding && <p className="note">{report.explanation_status === "abstained" ? "AI did not propose an explanation from the available evidence." : "No AI explanation passed verification."} The question below can guide an investigation; it does not explain the result.</p>}
    <section className="deep-priority-check" aria-label="Proposed next tests">
      <h3>Recommended next check</h3>
      {firstCheck && <ProposedTest item={firstCheck} report={report} result={result} />}
    </section>
    <div className="deep-supporting-details">
      {otherFindings.length > 0 && <ReportDisclosure label={`Other possible explanations (${otherFindings.length})`}>
        {otherFindings.map((item, index) => <article className="deep-item" key={index}>
          <h4>{item.title}</h4><p>{item.explanation}</p>
          <p className="note"><strong>Alternative:</strong> {item.alternative}</p>
          <ObservationProof report={report} result={result} ids={item.observation_ids} />
        </article>)}
      </ReportDisclosure>}
      {report.next_tests.length > 1 && <ReportDisclosure label={`Additional checks (${report.next_tests.length - 1})`}>
        {report.next_tests.slice(1).map((item, index) => <ProposedTest item={item} report={report} result={result} key={index} />)}
      </ReportDisclosure>}
      <ReportDisclosure label="What remains uncertain">
        <section className="deep-evidence-gaps" aria-label="Evidence gaps"><ul>{report.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul></section>
      </ReportDisclosure>
      {supporting.length > 0 && <ReportDisclosure label="Additional recorded inputs">
        {supporting.map(observation => <article className="deep-item" key={observation.id}><h4>{observation.title}</h4><p>{observation.text}</p></article>)}
      </ReportDisclosure>}
      <ReportDisclosure label={`All inspected patterns (${patterns.length} of ${report.pattern_count})`}>
        <p className="note">{report.inspected_cases} recorded fault cases inspected. {result.summary}</p>
        {patterns.map(observation => <article className="deep-item" key={observation.id}><h4>{observation.title}</h4><p>{observation.text}</p></article>)}
      </ReportDisclosure>
      <ReportDisclosure label="Scope and limitations"><ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></ReportDisclosure>
    </div>
    <p className="analysis-boundary">Saved automatically. These explanations need checking against evidence; they are not confirmed causes or deployment approval.</p>
  </div>;
}

function ReportDisclosure({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return <details className={`analysis-disclosure disclosure-plain ${className}`}><summary>{label}</summary>
    <div className="analysis-disclosure-content">{children}</div>
  </details>;
}

function ProposedTest({ item, report, result }: { item: DeepReport["next_tests"][number]; report: DeepReport; result: AnalysisResult }) {
  return <article className="deep-item deep-proposed-test">
    <h4>{item.title}</h4>
    {item.readiness && <p className="note"><strong>{item.readiness === "inspect_now" ? "Inspect recorded evidence" : "Collect evidence first"}</strong>{item.model && ` · ${item.model}`}</p>}
    {item.focus && <p>{item.focus}</p>}
    {(item.prerequisites?.length ?? 0) > 0 && <div className="deep-prerequisites"><strong>Needed before this check</strong><ul>{item.prerequisites!.map(value => <li key={value}>{value}</li>)}</ul></div>}
    <p>{item.procedure}</p>
    <details className="deep-outcomes disclosure-plain"><summary>How to interpret this check</summary>
      <div className="analysis-disclosure-content"><dl className="deep-test-outcome"><div><dt>Look for</dt><dd>{item.expected_signal}</dd></div><div><dt>What it would mean</dt><dd>{item.interpretation}</dd></div>{(item.controls?.length ?? 0) > 0 && <div><dt>Keep fixed</dt><dd>{item.controls!.join(" ")}</dd></div>}</dl></div>
    </details>
    <ObservationProof report={report} result={result} ids={item.observation_ids} />
  </article>;
}

function ObservationProof({ report, result, ids }: { report: DeepReport; result: AnalysisResult; ids: string[] }) {
  const observations = report.observations.filter(observation => ids.includes(observation.id));
  const references = new Set(observations.flatMap(observation => observation.source_ids));
  const label = observations.some(item => item.kind === "supporting") ? (observations.length === 1 ? "record" : "records") : (observations.length === 1 ? "pattern" : "patterns");
  return <ReportDisclosure className="deep-proof" label={`Recorded evidence (${observations.length} ${label})`}>
    {observations.map(observation => <article className="deep-item" key={observation.id}><h4>{observation.title}</h4><p>{observation.text}</p></article>)}
    <EvidenceContextCards sources={result.sources.filter(source => references.has(source.id))} variant="rows" />
  </ReportDisclosure>;
}
