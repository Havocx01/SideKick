import { Link, NavLink, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, ArrowUpRight, Database, FlaskConical, House, Layers, Plus } from "lucide-react";
import { api, experiments } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useExperimentId } from "../hooks/useEvidence";
import { EvidenceGuide } from "./EvidenceGuide";
import { ThemeToggle } from "./ThemeToggle";

export function Layout() {
  const health = useApi(() => api.health(), []);
  const id = useExperimentId();
  const location = useLocation();
  const [params] = useSearchParams();
  const context = new URLSearchParams();
  for (const key of ["candidate", "partition"]) { const value = params.get(key); if (value) context.set(key, value); }
  const record = useApi(() => (id ? experiments.get(id) : Promise.resolve(null)), [id, location.pathname]);
  const prefix = id ? `/experiments/${id}` : "";
  const isEvidence = ["comparison", "replay", "data", "benchmark", "walkthrough"].some(page => location.pathname.endsWith(`/${page}`));
  const views = [
    { to: "/", label: "Overview", icon: House },
    { to: "/experiments", label: "Experiments", icon: FlaskConical },
    { to: id ? `${prefix}/data` : "/benchmark", label: "Data and protocol", icon: Database },
    { to: `${prefix}/comparison`, label: "Model comparison", icon: Layers },
    { to: `${prefix}/replay`, label: "Warning replay", icon: Activity }
  ];
  const workspace = health.data?.mode === "replay" ? "Recorded demo" : health.data?.mode === "demo" ? "Hosted sample workspace" : "Local workspace";
  const currentView = views.find(view => view.to === location.pathname)?.label ?? (location.pathname === "/walkthrough" ? "Guided walkthrough" : location.pathname === "/new" ? "New experiment" : "Experiment progress");
  return (
    <div className={isEvidence ? "shell has-evidence-guide" : "shell"}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <Link to="/" className="brand" aria-label="Sidekick overview">
          <div className="brand-mark">Side<span>kick</span></div>
        </Link>
        {health.data?.can_train && <Link className="button sidebar-create" to="/new?source=sample" aria-label="New experiment" title="New experiment"><Plus size={18} aria-hidden="true" /><span>New experiment</span></Link>}
        <nav className="nav" aria-label="Main navigation">
          {views.filter(view => health.data?.can_train || view.to !== "/experiments").map(view => (
            <NavLink key={view.to} to={[`${prefix}/comparison`, `${prefix}/replay`, id ? `${prefix}/data` : "/benchmark"].includes(view.to) && context.size ? `${view.to}?${context}` : view.to} end title={view.label} aria-label={view.label}>
              <view.icon size={20} strokeWidth={1.75} aria-hidden="true" /><span>{view.label}</span>
            </NavLink>
          ))}
        </nav>
        {id && <Link className="benchmark-return" to="/comparison" aria-label="Recorded benchmark" title="Recorded benchmark"><ArrowLeft size={16} aria-hidden="true" /><span>Recorded benchmark</span></Link>}
        <div className="sidebar-foot">
          <div className="workspace-status"><span aria-hidden="true" className={health.data ? "status-dot connected" : "status-dot"} /><span>{health.data ? workspace : health.error ? "Server unavailable" : "Connecting"}</span></div>
          <span>Sidekick v1.5</span>
          {health.data?.mode !== "full" && <p>{health.data?.mode === "replay" ? "Recorded results only" : "Synthetic sample · results expire"}</p>}
          {health.error && <a href="">Retry connection</a>}
          <a href="https://github.com/Havocx01/SideKick" target="_blank" rel="noreferrer" className="repo-link">Source code <ArrowUpRight size={14} aria-hidden="true" /></a>
        </div>
      </aside>
      <main className="main" id="main-content" tabIndex={-1}>
        <header className="workspace-bar">
          <div className="breadcrumbs"><span>Workspace</span><span aria-hidden="true">/</span><span>{currentView}</span></div>
          <ThemeToggle />
        </header>
        <div className="main-inner">
          {isEvidence && (
            <div className="evidence-source" role="note">
              <Database size={18} strokeWidth={1.75} aria-hidden="true" />
              <div>
                <strong>{id ? record.data?.source === "synthetic" ? "Synthetic experiment" : record.data?.source === "upload" ? "Uploaded-data experiment" : "Experiment" : "Recorded NASA benchmark"}</strong>
                <span>{location.pathname === "/walkthrough" || params.get("partition") !== "holdout" ? "Development results" : "Final validation"} · {id && record.data?.source === "upload" ? "Field performance unverified" : "Not field validated"}</span>
              </div>
              <details className="source-details"><summary>About these results</summary><p>{id ? `${record.data ? new Date(record.data.created_at * 1000).toLocaleString() : "Loading source"} · ${id}` : "Simulated NASA data. Reserved histories were already examined and are not fresh validation."}</p></details>
            </div>
          )}
          {isEvidence && <a className="guide-jump" href="#evidence-guide">Jump to Evidence guide</a>}
          <Outlet key={id ?? "benchmark"} />
        </div>
      </main>
      {isEvidence && <EvidenceGuide key={id ?? "benchmark"} />}
    </div>
  );
}
