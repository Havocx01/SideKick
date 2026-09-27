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
  const isEvidence = ["comparison", "replay", "data", "benchmark"].some((page) => location.pathname.endsWith(`/${page}`));
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
        <div className="sidebar-header">
          <Link to="/" className="brand">
            <div className="brand-mark">
              Side<span>kick</span>
            </div>
            <div className="brand-tag">Test failure warnings before trusting them.</div>
          </Link>
          <ThemeToggle />
        </div>
        <div className="nav">
          {views .filter((view) => health.data?.can_train || view.to !== "/experiments")
            .map((view) => (
              <NavLink key={view.to} to={view.to} end>
                {view.label}
              </NavLink>
            ))}
        </div>
        {id && <Link to="/comparison">Back to recorded benchmark</Link>}
        <div className="sidebar-foot">
          {health.data ? (
            <>
              <strong>
                {health.data.mode === "replay"
                  ? "Recorded demo"
                  : health.data.mode === "demo" ? "Hosted sample workspace" : "Local workspace"}
              </strong>
              <p>
                {health.data.mode === "replay"
                  ? "Explore saved results. Training and upload are disabled."
                  : health.data.mode === "demo"
                    ? "Train on a compact synthetic sample. Export results within 24 hours; restarts and idle shutdowns may clear them sooner."
                    : "Training runs on your computer. No API key needed."}
              </p>
            </>
          ) : health.error ? ("Cannot reach the server. Refresh to try again.") : ("Connecting…")}
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
                      : record.data?.source === "upload" ? "Uploaded-data experiment" : "Experiment"}
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
