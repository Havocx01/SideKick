import type { ReactNode } from "react";

import { ApiError } from "../api/client";

export function Panel({ title, description, aside, tight, children }: {
  title: string;
  description?: ReactNode;
  aside?: ReactNode;
  tight?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {aside}
      </header>
      <div className={tight ? "panel-body tight" : "panel-body"}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note ? <div className="stat-note">{note}</div> : null}
    </div>
  );
}

export type Tone = "ok" | "bad" | "warn" | "info" | "neutral";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Callout({ tone, title, children }: { tone?: "fault" | "ok" | "warn"; title?: string; children: ReactNode; }) {
  return (
    <div className={tone ? `callout ${tone}` : "callout"}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}

export function Spinner({ size = "md", label }: { size?: "sm" | "md" | "lg"; label?: string }) {
  return (
    <div className={`cyber-spinner cyber-spinner-${size}`} role="status" aria-label={label || "Loading"}>
      <div className="spinner-core">
        <div className="spinner-ring outer" />
        <div className="spinner-ring inner" />
        <div className="spinner-dot" />
      </div>
      {label && <span className="spinner-label">{label}</span>}
    </div>
  );
}

export function StateBlock({
  loading,
  error,
  empty,
  loadingText = "Analyzing telemetry…",
  children
}: {
  loading?: boolean;
  error?: Error | null;
  empty?: boolean;
  loadingText?: string;
  children?: ReactNode;
}) {
  if (loading) {
    return (
      <div className="state loading-state">
        <Spinner size="md" label={loadingText} />
      </div>
    );
  }
  if (error) {
    const detail = error instanceof ApiError ? error.detail : undefined;
    return (
      <div className="state error">
        <div className="error-icon">!</div>
        <div className="error-body">
          <div className="error-title">{error.message}</div>
          {detail ? <code>{detail}</code> : null}
        </div>
      </div>
    );
  }
  if (empty) return <div className="state empty-state">Nothing recorded for this selection.</div>;
  return <>{children}</>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}
