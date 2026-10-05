import { useEvidence } from "../hooks/useEvidence";
import type { ProfileFinding, Severity } from "../api/types";
import { Badge, Callout, Panel, StateBlock, Stat, type Tone } from "../components/Chrome";
import { integer, number, percent } from "../format";
import { useApi } from "../hooks/useApi";

const SEVERITY_TONE: Record<Severity, Tone> = { info: "info", warning: "warn", blocker: "bad" };

export function DataSetup() {
  const api = useEvidence();
  const profile = useApi(() => api.profile(), [api]);
  const splits = useApi(() => api.splits(), [api]);
  const config = useApi(() => api.config(), [api]);
  const candidates = useApi(() => api.candidates(), [api]);
  const limitations = useApi(() => api.limitations(), [api]);

  const settings = (config.data?.config ?? {}) as Record<string, number>;
  const blockers = (profile.data?.findings ?? []).filter(f => f.severity === "blocker");

  return (
    <>
      <header className="page-head">
        <h1>Data setup</h1>
        <p>
          The evaluation contract: which histories are being used, what the profiler found wrong with them, and what
          counts as a useful warning. These settings are fixed before any model is trained, and the fingerprint below
          changes if any of them do.
        </p>
      </header>

      <StateBlock loading={profile.loading} error={profile.error}>
        {profile.data ? (
          <>
            {blockers.length > 0 ? (
              <Callout tone="fault" title="This data cannot be evaluated as configured">
                <ul>
                  {blockers.map(finding => (<li key={finding.code}>{finding.message}</li>))}
                </ul>
              </Callout>
            ) : null}

            <div className="grid cols-4">
              <Stat
                label="Equipment"
                value={integer(profile.data.equipment_count)}
                note="complete run-to-failure histories"
              />
              <Stat
                label="Readings"
                value={integer(profile.data.row_count)}
                note={`${profile.data.min_cycles}–${profile.data.max_cycles} cycles each`}
              />
              <Stat
                label="Channels"
                value={integer(profile.data.sensors.length)}
                note={`${profile.data.sensors.filter(s => s.varies).length} vary and are fault-tested`}
              />
              <Stat
                label="Inside the horizon"
                value={percent(profile.data.positive_label_fraction, 1)}
                note="share of scorable cycles labelled positive"
              />
            </div>

            <Panel
              title="What counts as a useful warning"
              description="Fixed before training."
            >
              <div className="grid cols-3" style={{ marginBottom: 0 }}>
                <Stat
                  label="Warning horizon"
                  value={`${settings.horizon_cycles ?? "—"} cycles`}
                  note="a cycle is positive if failure falls this close"
                />
                <Stat
                  label="Useful window"
                  value={`${settings.horizon_cycles ?? "—"}–${settings.min_useful_lead ?? "—"}`}
                  note="cycles before failure in which a warning is actionable"
                />
                <Stat
                  label="Late, not missed"
                  value={`≤ ${settings.late_window_end ?? "—"} cycles`}
                  note="a warning this late is reported separately"
                />
                <Stat
                  label="Alert rule"
                  value={`${settings.alert_on_consecutive ?? 2} up / ${settings.alert_off_consecutive ?? 2} down`}
                  note="consecutive scores needed to open and close an alert"
                />
                <Stat
                  label="Feature window"
                  value={`${settings.feature_window ?? "—"} cycles`}
                  note="current reading plus its trailing statistics"
                />
                <Stat
                  label="Alarm-free band"
                  value={`31–${settings.transition_band_end ?? "—"}`}
                  note="excluded from the early alarm burden"
                />
              </div>
            </Panel>

            <Panel
              title="Column roles"
              description="Sensor models exclude equipment IDs, cycle counts and failure targets."
              tight
            >
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Channel</th>
                      <th className="num">Mean</th>
                      <th className="num">Std dev</th>
                      <th className="num">Range</th>
                      <th className="num">Missing</th>
                      <th>Fault tested</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile.data.sensors.map(sensor => (
                      <tr key={sensor.name} className={sensor.varies ? undefined : "dimmed"}>
                        <td className="mono">{sensor.name}</td>
                        <td className="num">{number(sensor.mean, 2)}</td>
                        <td className="num">{number(sensor.std, 3)}</td>
                        <td className="num">
                          {number(sensor.minimum, 1)} – {number(sensor.maximum, 1)}
                        </td>
                        <td className="num">{percent(sensor.missing_fraction, 1)}</td>
                        <td>{sensor.varies ? <Badge tone="ok">yes</Badge> : <Badge tone="neutral">constant</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel
              title="Profile findings"
              description="Blockers must be resolved before training."
              tight
            >
              {(profile.data.findings ?? []).map((finding: ProfileFinding) => (
                <div className="finding" key={finding.code}>
                  <span className={`finding-dot ${finding.severity}`} />
                  <div>
                    <div className="finding-code">{finding.code}</div>
                    <div className="finding-msg">{finding.message}</div>
                  </div>
                  <div style={{ marginLeft: "auto" }}>
                    <Badge tone={SEVERITY_TONE[finding.severity]}>{finding.severity}</Badge>
                  </div>
                </div>
              ))}
            </Panel>
          </>
        ) : null}
      </StateBlock>

      <StateBlock loading={splits.loading} error={splits.error}>
        {splits.data ? (
          <Panel
            title="Partitions"
            description="Equipment stays separate across training and evaluation."
          >
            <div className="grid cols-3" style={{ marginBottom: 12 }}>
              <Stat
                label="Held back"
                value={integer(splits.data.holdout.length)}
                note={config.data?.holdout_status ?? "No automatic holdout scoring"}
              />
              <Stat
                label="Development"
                value={integer(splits.data.development.length)}
                note={`across ${splits.data.folds.length} grouped folds`}
              />
              <Stat
                label="Split seed"
                value={
                  <span className="mono" style={{ fontSize: 15 }}>
                    {splits.data.seed}
                  </span>
                }
                note="derived from the data hash, so it is reproducible"
              />
            </div>
            <p className="note">
              Held back: <span className="mono">{splits.data.holdout.join(", ")}</span>
            </p>
          </Panel>
        ) : null}
      </StateBlock>

      <StateBlock loading={candidates.loading} error={candidates.error}>
        {candidates.data ? (
          <Panel
            title="Candidates"
            description="Three sensor-based model families and an age-only baseline."
            tight
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Family</th>
                    <th>Configuration</th>
                    <th>Description</th>
                    <th>Reads sensors</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.data.map(candidate => (
                    <tr key={`${candidate.candidate}/${candidate.config_id}`}>
                      <td>{candidate.candidate.replace(/_/g, " ")}</td>
                      <td className="mono">{candidate.config_id}</td>
                      <td>{candidate.description}</td>
                      <td>
                        {candidate.uses_sensors ? <Badge tone="info">yes</Badge> : <Badge tone="neutral">no</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        ) : null}
      </StateBlock>

      {limitations.data ? (
        <Panel
          title="What this evaluation does not establish"
        >
          <ul className="limitations">
            {limitations.data.limitations.map(item => (<li key={item}>{item}</li>))}
          </ul>
        </Panel>
      ) : null}

      {profile.data && config.data ? (
        <p className="note">
          Data hash <span className="mono">{profile.data.data_hash}</span> · configuration{" "}
          <span className="mono">{config.data.config_fingerprint}</span>
          {config.data.git_commit ? (
            <>
              {" "}
              · commit <span className="mono">{config.data.git_commit}</span>
            </>
          ) : null}
          {config.data.source_digest ? (
            <>
              {" "}
              · source digest <span className="mono">{config.data.source_digest}</span>
            </>
          ) : (
            " · historical bundle: no source digest was recorded"
          )}
          {config.data.matches_current_code === false ? " · recorded with a different source version" : null}
        </p>
      ) : null}
    </>
  );
}
