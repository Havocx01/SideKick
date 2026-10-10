import { useEffect, useRef } from "react";
import { useAnalysis } from "./AnalysisProvider";
import { IconButton } from "./Chrome";
import { X } from "lucide-react";
import "./analysis.css";

// The provider stays mounted while the inspector's implementation loads.
export function DeferredAnalysisLoading() {
  const { close, context } = useAnalysis();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className={`analysis-inspector analysis-dialog${context?.task === "brief" ? " review-dialog" : ""}`}
    aria-label="Loading analysis" onCancel={event => { event.preventDefault(); close(); }}>
    <div className="analysis-dialog-inner">
      <header className="analysis-header"><h2>Analysis</h2><IconButton label="Close analysis" onClick={() => close()}><X size={17} aria-hidden="true" /></IconButton></header>
      <div className="analysis-body analysis-loading-body"><p role="status">Opening analysis…</p></div>
    </div>
  </dialog>;
}
