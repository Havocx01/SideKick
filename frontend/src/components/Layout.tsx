import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, ArrowUpRight, ChevronDown, Database, FlaskConical, House, Layers, PanelRight, Plus } from "lucide-react";
import { api, experiments } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useExperimentId } from "../hooks/useEvidence";
import { Button } from "./Chrome";
import { EvidenceGuide } from "./EvidenceGuide";
import { ThemeToggle } from "./ThemeToggle";

const GUIDE_KEY = "sidekick-guide";

function useDesktop() {
  const query = "(min-width: 901px)";
  const [desktop, setDesktop] = useState(() => typeof window === "undefined" || window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const sync = () => setDesktop(media.matches);
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  return desktop;
}

export function Layout() {
  const health = useApi(() => api.health(), []);
  const id = useExperimentId();
  const location = useLocation();
  const [params] = useSearchParams();
  const desktop = useDesktop();
  const [guideOpen, setGuideOpen] = useState(() => {
    try { return localStorage.getItem(GUIDE_KEY) !== "closed"; } catch { return true; }
  });
  const sourceRef = useRef<HTMLDetailsElement>(null);
  const context = new URLSearchParams();
  for (const key of ["candidate", "partition"]) { const value = params.get(key); if (value) context.set(key, value); }
  const record = useApi(() => (id ? experiments.get(id) : Promise.resolve(null)), [id, location.pathname]);
  const prefix = id ? `/experiments/${id}` : "";
  const isEvidence = ["comparison", "replay", "data", "benchmark", "walkthrough"].some(page => location.pathname.endsWith(`/${page}`));
  const guideCollapsed = isEvidence && desktop && !guideOpen;
  const views = [
    { to: "/", label: "Overview", icon: House },
    { to: "/experiments", label: "Experiments", icon: FlaskConical },
    { to: id ? `${prefix}/data` : "/benchmark", label: "Data and protocol", icon: Database },
    { to: `${prefix}/comparison`, label: "Model comparison", icon: Layers },
    { to: `${prefix}/replay`, label: "Warning replay", icon: Activity }
  ];
  const workspace = health.data?.mode === "replay" ? "Recorded demo" : health.data?.mode === "demo" ? "Hosted sample workspace" : "Local workspace";
  const currentView = views.find(view => view.to === location.pathname)?.label ?? (location.pathname === "/walkthrough" ? "Guided walkthrough" : location.pathname === "/new" ? "New experiment" : "Experiment progress");
  const sourceName = id ? record.data?.source === "synthetic" ? "Synthetic experiment" : record.data?.source === "upload" ? "Uploaded-data experiment" : "Experiment" : "Recorded NASA benchmark";
  const stage = location.pathname === "/walkthrough" || params.get("partition") !== "holdout" ? "Development results" : "Final validation";
  const validity = id && record.data?.source === "upload" ? "Field performance unverified" : "Not field validated";

  function toggleGuide() {
    setGuideOpen(open => {
      try { localStorage.setItem(GUIDE_KEY, open ? "closed" : "open"); } catch { /* preference is optional */ }
      return !open;
    });
  }

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
    <div className={["shell", isEvidence && "has-evidence-guide", guideCollapsed && "guide-collapsed"].filter(Boolean).join(" ")}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="Sidekick overview">
          <div className="brand-mark">Side<span>kick</span></div>
        </Link>
        {health.data?.can_train && <Link className="button sidebar-create" to="/new?source=sample" aria-label="New experiment" title="New experiment"><Plus size={16} aria-hidden="true" /><span>New experiment</span></Link>}
        <nav className="nav" aria-label="Main navigation">
          {views.filter(view => health.data?.can_train || view.to !== "/experiments").map(view => (
            <NavLink key={view.to} to={[`${prefix}/comparison`, `${prefix}/replay`, id ? `${prefix}/data` : "/benchmark"].includes(view.to) && context.size ? `${view.to}?${context}` : view.to} end title={view.label} aria-label={view.label}>
              <view.icon size={16} strokeWidth={1.9} aria-hidden="true" /><span>{view.label}</span>
            </NavLink>
          ))}
        </nav>
        {id && <Link className="benchmark-return" to="/comparison" aria-label="Recorded benchmark" title="Recorded benchmark"><ArrowLeft size={14} aria-hidden="true" /><span>Recorded benchmark</span></Link>}
        <div className="sidebar-foot">
          <div className="workspace-status"><span aria-hidden="true" className={health.data ? "status-dot connected" : "status-dot"} /><span>{health.data ? workspace : health.error ? "Server unavailable" : "Connecting"}</span></div>
          {health.data?.mode !== "full" && <p>{health.data?.mode === "replay" ? "Recorded results only" : "Synthetic sample · results expire"}</p>}
          {health.error && <a href="">Retry connection</a>}
          <a href="https://github.com/Havocx01/SideKick" target="_blank" rel="noreferrer" className="repo-link">Sidekick v1.5 · Source <ArrowUpRight size={12} aria-hidden="true" /></a>
        </div>
      </aside>
      <div className="workspace">
        <header className="workspace-bar">
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
          ) : <span className="toolbar-title">{currentView}</span>}
          <div className="toolbar-actions">
            {isEvidence && desktop && (
              <Button variant="ghost" className="icon-button guide-toggle" onClick={toggleGuide} aria-pressed={guideOpen} aria-label="Evidence guide" title={guideOpen ? "Hide Evidence guide" : "Show Evidence guide"}>
                <PanelRight size={17} strokeWidth={1.9} aria-hidden="true" />
              </Button>
            )}
            <ThemeToggle />
          </div>
        </header>
        <div className="workspace-body">
          <main className="main" id="main-content" tabIndex={-1}>
            <div className="main-inner">
              {isEvidence && <a className="guide-jump" href="#evidence-guide">Jump to Evidence guide</a>}
              <div className="page" key={location.pathname}>
                <Outlet key={id ?? "benchmark"} />
              </div>
            </div>
          </main>
          {isEvidence && <EvidenceGuide key={id ?? "benchmark"} collapsed={guideCollapsed} />}
        </div>
      </div>
    </div>
  );
}
