import type { ReactNode } from "react";

import { ApiError } from "../api/client";

export function Panel({
  title,
  description,
  aside,
  tight,
  children,
}: {
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

export function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
}) {
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

export function Callout({
  tone,
  title,
  children,
}: {
  tone?: "fault" | "ok" | "warn";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={tone ? `callout ${tone}` : "callout"}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}

/** Loading, error and empty states, so no view renders a blank page silently. */
export function StateBlock({
  loading,
  error,
  empty,
  children,
}: {
  loading?: boolean;
  error?: Error | null;
  empty?: boolean;
  children?: ReactNode;
}) {
  if (loading) return <div className="state">Loading…</div>;
  if (error) {
    const detail = error instanceof ApiError ? error.detail : undefined;
    return (
      <div className="state error">
        {error.message}
        {detail ? <code>{detail}</code> : null}
      </div>
    );
  }
  if (empty) return <div className="state">Nothing recorded for this selection.</div>;
  return <>{children}</>;
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}
