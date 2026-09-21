import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { CopilotPanel } from "./CopilotPanel";

/** The three views follow the order the work happens in, not alphabetical order. */
const VIEWS = [
  { to: "/", label: "Data setup", step: "1" },
  { to: "/comparison", label: "Model comparison", step: "2" },
  { to: "/replay", label: "Warning replay", step: "3" },
];

export function Layout() {
  const [copilotOpen, setCopilotOpen] = useState(false);
  const health = useApi(() => api.health(), []);

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            Side<span>kick</span>
          </div>
          <div className="brand-tag">
            Selects failure models by how their alerts survive sensor faults
          </div>
        </div>

        <div className="nav">
          {VIEWS.map((view) => (
            <NavLink key={view.to} to={view.to} end={view.to === "/"}>
              <span className="nav-step">{view.step}</span>
              {view.label}
            </NavLink>
          ))}
        </div>

        <div className="sidebar-foot">
          {health.data ? (
            <>
              <div>
                {health.data.mode === "replay"
                  ? "Serving recorded evidence. Training runs locally."
                  : "Local deployment."}
              </div>
              <dl>
                <dt>dataset</dt>
                <dd>{health.data.bundle.dataset_id ?? "none"}</dd>
                <dt>config</dt>
                <dd>{health.data.bundle.config_fingerprint ?? "—"}</dd>
                <dt>copilot</dt>
                <dd>{health.data.copilot}</dd>
              </dl>
            </>
          ) : health.error ? (
            <div>Backend unreachable.</div>
          ) : (
            <div>Connecting…</div>
          )}
        </div>
      </nav>

      <main className="main">
        <div className="main-inner">
          <Outlet />
        </div>
      </main>

      {copilotOpen ? (
        <CopilotPanel onClose={() => setCopilotOpen(false)} />
      ) : (
        <button className="copilot-toggle" onClick={() => setCopilotOpen(true)}>
          Ask the copilot
        </button>
      )}
    </div>
  );
}
