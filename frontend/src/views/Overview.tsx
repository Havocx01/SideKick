import { lazy, Suspense, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Badge, StateBlock } from "../components/Chrome";
import { useApi } from "../hooks/useApi";
import { ArrowRight, FlaskConical, Layers, Upload } from "lucide-react";
import { RollingNumber } from "../components/cult/RollingNumber";
import { shouldShowWalkthroughIntro } from "../lib/walkthrough-preference";
import { walkthroughPath } from "../walkthrough";
import { OverviewWarningMetric } from "../components/OverviewWarningMetric";
import { BorderBeamCard } from "../components/cult/BorderBeamCard";

const Walkthrough = lazy(() => import("./Walkthrough").then(module => ({ default: module.Walkthrough })));

export function Start() {
  const location = useLocation();
  const navigate = useNavigate();
  const autoOpened = useRef(false);
  const walkthroughOpen = location.pathname === "/walkthrough";
  useEffect(() => {
    if (walkthroughOpen || autoOpened.current) return;
    autoOpened.current = true;
    if (shouldShowWalkthroughIntro()) navigate(walkthroughPath("clean"), { replace: true });
  }, [walkthroughOpen, navigate]);
  const health = useApi(() => api.health(), []);
  const selection = useApi(() => api.selection(), []);
  const example = selection.data?.ranked.find(row => row.candidate === "logistic_regression" && row.config_id === "lr2");
  return (
    <>
      {walkthroughOpen && <Suspense fallback={null}><Walkthrough /></Suspense>}
      <section className="welcome" aria-labelledby="welcome-heading">
        <div>
          <h1 id="welcome-heading">Will warnings survive sensor faults?</h1>
          <p>Train failure-warning models. Test them with missing, stuck or drifting readings.</p>
          <div className="hero-actions">
            <Link id="open-walkthrough" className="button contrast" to={walkthroughPath("clean")}>View walkthrough <ArrowRight size={16} aria-hidden="true" /></Link>
          </div>
          <p className="hero-footnote"><RollingNumber value={5} /> steps · Recorded results</p>
        </div>
        <BorderBeamCard cardClassName="benchmark-preview">
          <div className="preview-heading"><h2>Warnings in time</h2><Badge>Recorded NASA Benchmark</Badge></div>
          <div className="preview-subtitle">Logistic regression · lr2</div>
          <StateBlock loading={selection.loading} error={selection.error}>
            {example ? (
              <>
                <div className="benchmark-bars">
                  <OverviewWarningMetric label="Healthy sensors" detected={example.clean.detected} histories={example.clean.engines} fraction={example.clean.detection_fraction} />
                  <OverviewWarningMetric label="Weakest sensor fault" detected={example.worst_metrics?.detected} histories={example.worst_metrics?.engines} fraction={example.worst_detection_required} fault />
                </div>
                {/* <div className="preview-explanation">
                  <details><summary>What was tested?</summary><p>{scenarioLabel(example.worst_scenario_id ?? "")}. Warnings active 10–30 cycles before failure. Simulated NASA data, not ABB field validation.</p></details>
                  <Link to="/comparison?candidate=logistic_regression%2Flr2">Inspect the evidence <ArrowRight size={16} aria-hidden="true" /></Link>
                </div> */}
              </>
            ) : <p className="note">Open the recorded comparison to inspect the available candidates and fault tests.</p>}
          </StateBlock>
        </BorderBeamCard>
      </section>
      <section className="start-section" aria-labelledby="start-heading">
        <h2 id="start-heading">Start an experiment</h2>
        <StateBlock loading={health.loading} error={health.error}>
          <div className="start-actions">
            <section>
              <div className="start-option"><Layers size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Recorded benchmark</h3><p>NASA data</p></div></div>
              <Link className="button" to="/comparison">Explore benchmark <ArrowRight size={16} aria-hidden="true" /></Link>
            </section>
            <section>
              <div className="start-option"><FlaskConical size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Sample experiment</h3><p><RollingNumber value={health.data?.sample_equipment ?? 60} /> simulated histories</p></div></div>
              {health.data?.can_train ? <Link className="button" to="/new?source=sample">Set up sample <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
            <section>
              <div className="start-option"><Upload size={20} strokeWidth={1.75} aria-hidden="true" /><div><h3>Your data</h3><p>CSV · Up to <RollingNumber value={10} /> MB · Complete failure histories</p></div></div>
              {health.data?.can_upload ? <Link className="button" to="/new?source=upload">Upload CSV <ArrowRight size={16} aria-hidden="true" /></Link> : <span className="option-unavailable">Available in the local app</span>}
            </section>
          </div>
        </StateBlock>
      </section>
      <p className="scope-note">Development evidence · Not field validated</p>
      {health.data?.mode === "demo" && <details><summary>Hosted sample limits</summary><p className="note">30 short histories, three sensors and four configurations. Two runs per browser per hour, one active server run, and shared daily limits apply. Results expire after 24 hours or sooner after a restart. Export evidence to keep it.</p></details>}
    </>
  );
}

