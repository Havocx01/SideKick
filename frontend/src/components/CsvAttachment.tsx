import { FileSpreadsheet, LoaderCircle, RotateCcw, X } from "lucide-react";
import { IconButton } from "./Chrome";

export function CsvAttachment({ name, size, state, error, disabled, onRemove, onRetry }: {
  name: string;
  size?: number;
  state: "uploading" | "ready" | "error";
  error?: string;
  disabled?: boolean;
  onRemove: () => void;
  onRetry?: () => void;
}) {
  const fileSize = size == null ? null : size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return <div className="csv-attachment" data-state={state} aria-busy={state === "uploading"}>
    <span className="csv-attachment-media" aria-hidden="true">{state === "uploading" ? <LoaderCircle size={20} className="run-spinner" /> : <FileSpreadsheet size={20} />}</span>
    <div className="csv-attachment-content">
      <p className="csv-attachment-title">{name}</p>
      <p className="csv-attachment-description" role="status">CSV{fileSize && ` · ${fileSize}`} · {state === "uploading" ? "Uploading…" : state === "error" ? "Upload failed" : "Attached"}</p>
      {state === "error" && error && <p className="csv-attachment-error" role="alert">{error}</p>}
    </div>
    <div className="csv-attachment-actions">
      {state === "error" && onRetry && <IconButton label={`Retry upload of ${name}`} disabled={disabled} onClick={onRetry}><RotateCcw size={16} aria-hidden="true" /></IconButton>}
      <IconButton label={state === "uploading" ? "Cancel CSV upload" : `Remove ${name}`} disabled={disabled} onClick={onRemove}><X size={16} aria-hidden="true" /></IconButton>
    </div>
  </div>;
}
