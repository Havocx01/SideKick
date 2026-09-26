import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { api, experiments } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useExperimentId } from "../hooks/useEvidence";
import { EvidenceGuide } from "./EvidenceGuide";

import { ThemeToggle } from "./ThemeToggle";

export function Layout() {
  const health = useApi(() => api.health(), []);
  const id = useExperimentId();
  const location = useLocation();
  const record = useApi(() => (id ? experiments.get(id) : Promise.resolve(null)), [id, location.pathname]);
  const prefix = id ? `/experiments/${id}` : "";
  const isEvidence = ["comparison", "replay", "data", "benchmark"].some(p => location.pathname.endsWith(`/${p}`));
  const views = [
    { to: "/", label: "Start here" },
    { to: "/experiments", label: "Your experiments" },
    { to: id ? `${prefix}/data` : "/benchmark", label: "Data and protocol" },
    { to: `${prefix}/comparison`, label: "Model comparison" },
    { to: `${prefix}/replay`, label: "Warning replay" }
  ];
  return (
    <div className={isEvidence ? "shell has-evidence-guide" : "shell"}>
      <nav className="sidebar" aria-label="Main navigation">
        <Link to="/" className="brand">
          <div className="brand-header-row">
            <div className="brand-mark">
              Side<span>kick</span>
            </div>
            <span className="brand-status-dot" title="System online" />
          </div>
          <div className="brand-tag">Test failure warnings before trusting them.</div>
        </Link>
        <div className="nav">
          {views
            .filter(v => health.data?.can_train || v.to !== "/experiments")
            .map(v => (
              <NavLink key={v.to} to={v.to} end>
                {v.label}
              </NavLink>
            ))}
        </div>
        {id && (
          <Link to="/comparison" className="nav-benchmark-link">
            <span className="nav-arrow">←</span> Back to recorded benchmark
          </Link>
        )}
        <div className="sidebar-theme-container">
          <ThemeToggle />
        </div>
        <div className="sidebar-foot">
          {health.data ? (
            <>
              <div className="system-status-indicator">
                <span className={`status-beacon ${health.data.mode === "replay" ? "beacon-warn" : "beacon-live"}`} />
                <strong>{health.data.mode === "replay" ? "Recorded demo" : "Local workspace"}</strong>
              </div>
              <p>
                {health.data.mode === "replay"
                  ? "Explore saved results. Training and upload are disabled."
                  : "Training runs locally on your engine. Zero API key needed."}
              </p>
            </>
          ) : health.error ? (
            <div className="system-status-indicator">
              <span className="status-beacon beacon-error" />
              <span>Backend unreachable. Check server.</span>
            </div>
          ) : (
            <div className="system-status-indicator">
              <span className="status-beacon beacon-pulse" />
              <span>Connecting to telemetry engine…</span>
            </div>
          )}
        </div>
      </nav>
      <main className="main">
        <div className="main-inner">
          {isEvidence && (
            <div className="evidence-source" role="note">
              {id ? (
                <>
                  <strong>
                    {record.data?.source === "synthetic"
                      ? "Synthetic experiment"
                      : record.data?.source === "upload" ? "Uploaded-data experiment" : "Local experiment"}
                  </strong>
                  <span>
                    {record.data ? new Date(record.data.created_at * 1000).toLocaleString() : "Loading source…"} ·{" "}
                    {id.slice(0, 8)}
                  </span>
                </>
              ) : (
                <>
                  <strong>Recorded NASA benchmark</strong>
                  <span>
                    Previously evaluated holdout engines are exposed. These results do not validate ABB field
                    performance.
                  </span>
                </>
              )}
            </div>
          )}
          {isEvidence && (
            <a className="guide-jump" href="#evidence-guide">
              Jump to Evidence guide
            </a>
          )}
          <Outlet key={id ?? "benchmark"} />
        </div>
      </main>
      {isEvidence && <EvidenceGuide key={id ?? "benchmark"} />}
    </div>
  );
}
