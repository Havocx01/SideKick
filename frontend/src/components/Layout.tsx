import { useEffect, useRef } from "react";
import { Link, NavLink, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { Activity, ArrowUpRight, ChevronDown, ClipboardCheck, Database, FlaskConical, House, Layers, Plus } from "lucide-react";
import { api, experiments } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useExperimentId } from "../hooks/useEvidence";
import { AnalysisProvider } from "./AnalysisProvider";
import { AnalysisInspector } from "./AnalysisInspector";
import { ThemeToggle } from "./ThemeToggle";
import { Toaster } from "@/components/ui/toast";
import { TrainingNotifications } from "./TrainingNotifications";
import { CanvasFractalGrid } from "./cult/CanvasFractalGrid";

export function Layout() {
  return <AnalysisProvider><Workspace /></AnalysisProvider>;
}
function Workspace() {
  const health = useApi(() => api.health(), []);
  const id = useExperimentId();
  const location = useLocation();
  const [params] = useSearchParams();
  const sourceRef = useRef<HTMLDetailsElement>(null);
  const context = new URLSearchParams();
  for (const key of ["candidate", "partition"]) { const value = params.get(key); if (value) context.set(key, value); }
  const record = useApi(() => (id ? experiments.get(id) : Promise.resolve(null)), [id, location.pathname]);
  const prefix = id ? `/experiments/${id}` : "";
  const isEvidence = ["comparison", "replay", "data", "benchmark"].some(page => location.pathname.endsWith(`/${page}`));
  const pilotReady = Boolean(id && health.data?.can_review_pilot && record.data?.status === "completed");
  const sections = [
    { title: "Workspace", views: [
      { to: "/", label: "Overview", icon: House },
      ...(health.data?.can_train ? [{ to: "/experiments", label: "Experiments", icon: FlaskConical }] : [])
    ] },
    { title: "Evidence", views: [
      { to: id ? `${prefix}/data` : "/benchmark", label: "Data and protocol", icon: Database },
      { to: `${prefix}/comparison`, label: "Model comparison", icon: Layers },
      { to: `${prefix}/replay`, label: "Warning replay", icon: Activity }
    ] },
    { title: "Pilot", views: pilotReady ? [{ to: `${prefix}/pilot`, label: "Equipment pilot", icon: ClipboardCheck }] : [] }
  ];
  const views = sections.flatMap(section => section.views);
  const workspace = health.data?.mode === "replay" ? "Recorded demo" : health.data?.mode === "demo" ? "Hosted sample workspace" : "Local workspace";
  const workspacePath = location.pathname === "/walkthrough" ? "/" : location.pathname;
  const activeView = views.find(view => view.to === workspacePath);
  const currentView = activeView?.label ?? (location.pathname === "/walkthrough" ? "Guided walkthrough" : location.pathname.endsWith("/pilot") ? "Equipment pilot" : location.pathname === "/new" ? "New experiment" : "Experiment progress");
  const sectionName = sections.find(section => section.views.some(view => view.to === workspacePath))?.title ?? (isEvidence ? "Evidence" : location.pathname.endsWith("/pilot") ? "Pilot" : "Workspace");
  const sectionHref = sectionName === "Evidence" ? `${prefix}/comparison` : sectionName === "Pilot" ? "/experiments" : "/";
  const PageIcon = activeView?.icon ?? (isEvidence ? Layers : location.pathname.endsWith("/pilot") ? ClipboardCheck : FlaskConical);
  const isOverview = location.pathname === "/" || location.pathname === "/walkthrough";
  const sourceName = id ? record.data?.source === "synthetic" ? "Synthetic experiment" : record.data?.source === "upload" ? "Uploaded-data experiment" : "Experiment" : "Recorded NASA benchmark";
  const stage = location.pathname === "/walkthrough" || params.get("partition") !== "holdout" ? "Development results" : "Final validation";
  const validity = id && record.data?.source === "upload" ? "Field performance unverified" : "Not field validated";

  useEffect(() => {
    const close = (event: PointerEvent | KeyboardEvent) => {
      const source = sourceRef.current;
      if (!source?.open) return;
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !source.contains(event.target as Node)) source.open = false;
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", close); };
  }, []);

  return (
    <div className="shell">
      <TrainingNotifications enabled={Boolean(health.data?.can_train)} />
      <Toaster />
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="Sidekick overview">
          <div className="brand-mark">Side<span>kick</span></div>
        </Link>
        {health.data?.can_train && <Link className="button sidebar-create" to="/new?source=sample" aria-label="New experiment" title="New experiment"><Plus size={16} aria-hidden="true" /><span>New experiment</span></Link>}
        <nav className="nav" aria-label="Main navigation">
          {sections.map(section => (
            <div className="nav-section" role="group" aria-labelledby={`nav-${section.title}`} key={section.title}>
              <h2 className="nav-heading" id={`nav-${section.title}`}>{section.title}</h2>
              {section.views.map(view => (
                <NavLink key={view.to} to={[`${prefix}/comparison`, `${prefix}/replay`, id ? `${prefix}/data` : "/benchmark"].includes(view.to) && context.size ? `${view.to}?${context}` : view.to} end title={view.label} aria-label={view.label}>
                  <view.icon size={16} strokeWidth={1.9} aria-hidden="true" /><span>{view.label}</span>
                </NavLink>
              ))}
              {section.title === "Pilot" && !pilotReady && health.data && (health.data.can_review_pilot
                ? <Link className="nav-pending" to="/experiments" title="Open a completed experiment to review an equipment pilot" aria-label="Equipment pilot: choose a completed experiment"><ClipboardCheck size={16} strokeWidth={1.9} aria-hidden="true" /><span>Equipment pilot</span></Link>
                : <span className="nav-disabled" aria-disabled="true" title="Equipment pilots are available in a local workspace"><ClipboardCheck size={16} strokeWidth={1.9} aria-hidden="true" /><span>Equipment pilot</span></span>)}
            </div>
          ))}
        </nav>
        {/* {id && <Link className="benchmark-return" to="/comparison" aria-label="Recorded benchmark" title="Recorded benchmark"><ArrowLeft size={14} aria-hidden="true" /><span>Recorded benchmark</span></Link>} */}
        <div className="sidebar-foot">
          <div className="workspace-status"><span aria-hidden="true" className={health.data ? "status-dot connected" : "status-dot"} /><span>{health.data ? workspace : health.error ? "Server unavailable" : "Connecting"}</span></div>
          {health.data?.mode !== "full" && <p>{health.data?.mode === "replay" ? "Recorded results only" : "Synthetic sample · results expire"}</p>}
          {health.error && <a href="">Retry connection</a>}
          <a href="https://github.com/Havocx01/SideKick" target="_blank" rel="noreferrer" className="repo-link">Sidekick v2.0 · Source <ArrowUpRight size={12} aria-hidden="true" /></a>
        </div>
      </aside>
      <div className="workspace">
        <header className="workspace-bar">
          <nav className="workspace-breadcrumb" aria-label="Breadcrumb">
            <ol><li><Link to={sectionHref}>{sectionName}</Link></li><li className="breadcrumb-divider" aria-hidden="true">/</li><li className="breadcrumb-current" aria-current="page"><PageIcon size={15} strokeWidth={1.9} aria-hidden="true" /><span>{currentView}</span></li></ol>
          </nav>
          <div className="toolbar-actions">
          {isEvidence ? (
            <details className="source-chip" ref={sourceRef}>
              <summary aria-label={`${sourceName}. ${stage}. ${validity}. About these results`}>
                <Database size={14} strokeWidth={2} aria-hidden="true" />
                <strong>{sourceName}</strong>
                <span className="source-sep" aria-hidden="true" />
                <span className="source-detail">{stage}</span>
                <ChevronDown size={12} strokeWidth={2.4} aria-hidden="true" />
              </summary>
              <div className="source-popover">
                <p><strong>{stage}</strong> · {validity}</p>
                <p>{id ? `${record.data ? new Date(record.data.created_at * 1000).toLocaleString() : "Loading source"} · ${id}` : "Simulated NASA data. Reserved histories were already examined and are not fresh validation."}</p>
              </div>
            </details>
          ) : null}
            <ThemeToggle />
          </div>
        </header>
        <div className={`workspace-body${isOverview ? " overview-workspace" : ""}`}>
          {isOverview && <CanvasFractalGrid waveIntensity={36} enableMouseGlow={false} respectReducedMotion={false} />}
          <main className={`main${isOverview ? " overview-main" : ""}`} id="main-content" tabIndex={-1}>
            <div className="main-inner">
              <div className={`page${isOverview ? " page-overview" : ""}`} key={isOverview ? "overview" : location.pathname}>
                <Outlet key={id ?? "benchmark"} />
              </div>
            </div>
          </main>
          <AnalysisInspector />
        </div>
      </div>
    </div>
  );
}
