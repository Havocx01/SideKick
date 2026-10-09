import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/arc/tabs/tabs";
import { SortableDataTable, type DataColumn } from "@/components/arc/sortable-data-table/sortable-data-table";
import { SearchField } from "@/components/arc/search-field/search-field";
import { Alert } from "@/components/arc/alert/alert";
import { CopyButton } from "@/components/arc/copy-button/copy-button";
import { Skeleton } from "@/registry/components/skeleton/skeleton";
import { ArrowRight } from "lucide-react";
import { useEvidence, useExperimentId } from "../hooks/useEvidence";
import type { CandidateConfig, DatasetProfile, SensorProfile, Severity } from "../api/types";
import { Badge, Button, Stat, type Tone } from "../components/Chrome";
import { WarningTiming, DataSeparation } from "../components/ProtocolDiagrams";
import { integer, number, percent } from "../format";
import { useApi, type AsyncState } from "../hooks/useApi";
import { protocolSearch, protocolView } from "../lib/dataProtocol";
import styles from "./data-protocol.module.css";

const severityTone: Record<Severity, Tone> = { info: "info", warning: "warn", blocker: "bad" };
type SensorRow = SensorProfile & Record<string, unknown>;
const sensorColumns: DataColumn<SensorRow>[] = [
  { key: "name", label: "Channel", render: value => <code>{String(value)}</code> },
  { key: "mean", label: "Mean", numeric: true, render: (_, row) => number(row.mean, 2) },
  { key: "std", label: "Standard deviation", numeric: true, render: (_, row) => number(row.std, 3) },
  { key: "minimum", label: "Range", numeric: true, render: (_, row) => `${number(row.minimum, 1)} – ${number(row.maximum, 1)}` },
  { key: "missing_fraction", label: "Missing", numeric: true, render: (_, row) => percent(row.missing_fraction, 1) },
  { key: "varies", label: "Readings vary", render: (_, row) => <Badge tone={row.varies ? "info" : "neutral"}>{row.varies ? "Yes" : "Constant"}</Badge> },
];
type CandidateRow = CandidateConfig & Record<string, unknown>;
const candidateColumns: DataColumn<CandidateRow>[] = [
  { key: "candidate", label: "Family", render: value => String(value).replace(/_/g, " ") },
  { key: "config_id", label: "Configuration", render: value => <code>{String(value)}</code> },
  { key: "description", label: "Description", sortable: false, render: value => String(value || "Unavailable") },
  { key: "uses_sensors", label: "Reads sensors", render: value => <Badge tone={value ? "info" : "neutral"}>{value === true ? "Yes" : value === false ? "No" : "Unavailable"}</Badge> },
];

export function DataSetup() {
  const api = useEvidence();
  const experimentId = useExperimentId();
  const [params, setParams] = useSearchParams();
  const view = protocolView(params.get("view"));
  const profile = useApi(() => api.profile(), [api]);
  const splits = useApi(() => api.splits(), [api]);
  const config = useApi(() => api.config(), [api]);
  const candidates = useApi(() => api.candidates(), [api]);
  const limitations = useApi(() => api.limitations(), [api]);
  const focusFindings = useRef(false);
  const technicalRef = useRef<HTMLDivElement>(null);
  useEffect(() => { focusFindings.current = false; }, [experimentId]);
  useEffect(() => {
    if (view !== "technical" || !focusFindings.current) return;
    const frame = requestAnimationFrame(() => {
      technicalRef.current?.querySelector<HTMLElement>("section")?.focus({ preventScroll: true });
      focusFindings.current = false;
    });
    return () => cancelAnimationFrame(frame);
  }, [view]);
  function changeView(next: string) {
    setParams(previous => protocolSearch(previous, next));
  }
  function showFindings() {
    focusFindings.current = true;
    changeView("technical");
  }
  const findings = profile.data?.findings ?? [];
  const blockers = findings.filter(item => item.severity === "blocker");
  const warningCount = findings.filter(item => item.severity === "warning").length;
  const contextKey = experimentId ?? "benchmark";
  return <div className={styles.page}>
    <header className={styles.heading}><h1>Data and protocol</h1><p>Recorded data, warning rules and validation splits.</p></header>
    {blockers.length > 0 && <Alert tone="danger" title="This data cannot be evaluated as configured"><ul>{blockers.map(item => <li key={item.code}>{item.message}</li>)}</ul></Alert>}
    <Tabs className={styles.tabs} value={view} onValueChange={changeView}>
      <TabsList aria-label="Data and protocol views"><TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="sensors">Sensors</TabsTrigger><TabsTrigger value="technical">Technical</TabsTrigger></TabsList>
      <TabsContent value="overview">
        <EvidenceState state={profile} label="Data summary">{profile.data && <>
          <div className={styles.summary}>
            <Stat label="Equipment" value={integer(profile.data.equipment_count)} note="failure histories" />
            <Stat label="Readings" value={integer(profile.data.row_count)} note={`${number(profile.data.min_cycles, 0)}–${number(profile.data.max_cycles, 0)} cycles`} />
            <Stat label="Channels" value={integer(profile.data.sensors.length)} note={`${profile.data.sensors.filter(item => item.varies).length} varying`} />
          </div>
          <div className={styles.findingsSummary}><span>{blockers.length ? `${blockers.length} recorded blocker${blockers.length === 1 ? "" : "s"}` : profile.data.usable === false ? "Data is recorded as unusable" : "No recorded blockers"}{warningCount ? ` · ${warningCount} warning${warningCount === 1 ? "" : "s"}` : ""}</span><Button variant="ghost" size="sm" onClick={showFindings}>View findings <ArrowRight size={14} /></Button></div>
        </>}</EvidenceState>
        <div className={styles.overviewPanels} key={contextKey}>
          <EvidenceState state={config} label="Warning protocol">{config.data && <WarningTiming config={config.data} positiveFraction={profile.data?.positive_label_fraction} />}</EvidenceState>
          <EvidenceState state={splits} label="Equipment assignments">{splits.data && <DataSeparation splits={splits.data} config={config.data} profile={profile.data} />}</EvidenceState>
        </div>
      </TabsContent>
      <TabsContent value="sensors"><EvidenceState state={profile} label="Sensor records">{profile.data && <SensorRecords key={contextKey} profile={profile.data} />}</EvidenceState></TabsContent>
      <TabsContent value="technical"><div className={styles.technical} ref={technicalRef}>
        <TechnicalSection title={`Data findings (${findings.length})`}>
          <EvidenceState state={profile} label="Data findings"><div className={styles.findings}>{findings.map(item => <div key={item.code}><span><strong>{item.message}</strong><code>{item.code}</code></span><Badge tone={severityTone[item.severity]}>{item.severity}</Badge></div>)}</div>{profile.data && findings.length === 0 && <p>No findings are recorded. This does not establish deployment readiness.</p>}</EvidenceState>
        </TechnicalSection>
        <TechnicalSection title="Equipment assignments">
          <EvidenceState state={splits} label="Equipment assignments">{splits.data && <>
            <p>{config.data?.holdout_status || "No reserved-history status is recorded."}</p>
            <dl className={`${styles.ruleList} ${styles.identifiers}`}>
              <div><dt>Development ({splits.data.development.length})</dt><dd>{splits.data.development.join(", ") || "No assignments recorded"}</dd></div>
              <div><dt>Reserved validation ({splits.data.holdout.length})</dt><dd>{splits.data.holdout.join(", ") || "No assignments recorded"}</dd></div>
              {splits.data.folds.map((fold, index) => <div key={index}><dt>Fold {index + 1} validation equipment</dt><dd>{fold.join(", ") || "No assignments recorded"}</dd></div>)}
              <div><dt>Split seed</dt><dd>{splits.data.seed ?? "Not recorded"}</dd></div>
            </dl>
          </>}</EvidenceState>
        </TechnicalSection>
        <TechnicalSection title="Model configurations">
          <EvidenceState state={candidates} label="Model configurations">{candidates.data && <><p className={styles.inlineNote}>Sensor models exclude equipment IDs, cycle counts and failure targets. The age-only baseline does not read sensors.</p><SortableDataTable rows={candidates.data.map(item => ({ ...item }))} columns={candidateColumns} rowKey={row => `${row.candidate}/${row.config_id}`} caption="Recorded model configurations" defaultSort={{ key: "candidate", direction: "asc" }} selectable={false} emptyMessage="No model configurations are recorded." /></>}</EvidenceState>
        </TechnicalSection>
        <TechnicalSection title="Evaluation limits">
          <EvidenceState state={limitations} label="Evaluation limits">{limitations.data && (limitations.data.limitations.length ? <ul>{limitations.data.limitations.map(item => <li key={item}>{item}</li>)}</ul> : <p>No evaluation limits are recorded. This does not establish deployment approval.</p>)}</EvidenceState>
        </TechnicalSection>
        <TechnicalSection title="Source identifiers">
          <EvidenceState state={profile} label="Data identifier"><EvidenceState state={config} label="Source identifiers">{profile.data && config.data && <>
            <dl className={`${styles.sourceList} ${styles.identifiers}`}>
              <SourceIdentifier label="Data hash" value={profile.data.data_hash} />
              <SourceIdentifier label="Configuration fingerprint" value={config.data.config_fingerprint} />
              <SourceIdentifier label="Source commit" value={config.data.git_commit} />
              <SourceIdentifier label="Source digest" value={config.data.source_digest} />
            </dl>
            {!config.data.source_digest && <p className={styles.inlineNote}>Historical bundle: no source digest was recorded.</p>}
            {config.data.matches_current_code === false && <p className={styles.inlineNote}>Recorded with a different source version.</p>}
          </>}</EvidenceState></EvidenceState>
        </TechnicalSection>
      </div></TabsContent>
    </Tabs>
  </div>;
}

function TechnicalSection({ title, children }: { title: string; children: ReactNode }) {
  const titleId = useId();
  return <section className={styles.technicalSection} aria-labelledby={titleId} tabIndex={-1}>
    <h2 id={titleId} className={styles.technicalHeading}>{title}</h2>
    <div className={styles.technicalContent}>{children}</div>
  </section>;
}

function SensorRecords({ profile }: { profile: DatasetProfile }) {
  const [search, setSearch] = useState("");
  const rows: SensorRow[] = profile.sensors.filter(item => item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).map(item => ({ ...item }));
  return <section>
    <div className={styles.sensorToolbar}><div><h2>Sensor records</h2><p>Equipment IDs, cycles and failure targets are excluded from sensor-model inputs.</p></div><SearchField label="Search channels" placeholder="Channel name" value={search} onValueChange={setSearch} /></div>
    <p className={styles.inlineNote} aria-live="polite">{rows.length} of {profile.sensors.length} channels · Missing values are shown as —. Range sorts by its minimum.</p>
    <SortableDataTable rows={rows} columns={sensorColumns} rowKey={row => row.name} caption="Recorded sensor statistics" selectable={false} defaultSort={{ key: "name", direction: "asc" }} emptyMessage={search.trim() ? `No channels match “${search.trim()}”. Clear the search to see all channels.` : "No sensor records are available."} />
  </section>;
}

function EvidenceState({ state, label, children }: { state: Pick<AsyncState<unknown>, "loading" | "error" | "reload">; label: string; children: ReactNode }) {
  if (state.loading) return <div className={styles.loading} aria-label={`Loading ${label.toLowerCase()}`}><Skeleton lines={3} /></div>;
  if (state.error) return <Alert tone="danger" title={`${label} could not be loaded`}><p>{state.error.message}</p><Button variant="secondary" size="sm" onClick={state.reload}>Try again</Button></Alert>;
  return <>{children}</>;
}
function SourceIdentifier({ label, value }: { label: string; value?: string | null }) {
  return <div><dt>{label}</dt><dd><code>{value || "Not recorded"}</code>{value && <CopyButton value={value} variant="plain" iconOnly label={`Copy ${label.toLowerCase()}`} />}</dd></div>;
}
