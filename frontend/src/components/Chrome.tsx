import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { Badge as ArcBadge } from "@/registry/components/badge/badge";
import { Skeleton } from "@/registry/components/skeleton/skeleton";
import { AlertCircle, Inbox } from "lucide-react";
import { Button } from "@/registry/components/button/button";
import type { ButtonProps } from "@/registry/components/button/button";

export { Button } from "@/registry/components/button/button";
export { Select } from "@/registry/components/select/select";

export function IconButton({ label, className, variant = "ghost", ...props }: ButtonProps & { label: string }) {
  return <Button {...props} variant={variant} className={`action-icon${className ? ` ${className}` : ""}`} aria-label={label} title={label} />;
}

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
  const tones = { ok: "success", bad: "danger", warn: "warning", info: "info", neutral: "neutral" } as const;
  return <ArcBadge tone={tones[tone]} size="sm">{children}</ArcBadge>;
}

export function Callout({ tone, title, children }: { tone?: "fault" | "ok" | "warn"; title?: string; children: ReactNode; }) {
  return (
    <div className={tone ? `callout ${tone}` : "callout"}>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}

export function StateBlock({ loading, error, empty, children }: {
  loading?: boolean;
  error?: Error | null;
  empty?: boolean;
  children?: ReactNode;
}) {
  if (loading) return <div className="loading-state"><Skeleton lines={3} label="Loading evidence" /></div>;
  if (error) {
    const detail = error instanceof ApiError ? error.detail : undefined;
    return (
      <div className="state error" role="alert">
        <AlertCircle size={20} aria-hidden="true" />
        <p>{error.message}</p>
        {detail ? <code>{detail}</code> : null}
        <a href="">Retry this page</a>
      </div>
    );
  }
  if (empty) return <div className="state"><Inbox size={24} aria-hidden="true" /><p>Nothing recorded for this selection.</p></div>;
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
