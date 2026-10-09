import { useRef, useState, type DragEventHandler, type KeyboardEventHandler, type MouseEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ContextMenu } from "@base-ui/react/context-menu";
import { Menu } from "@base-ui/react/menu";
import { Check, FileSpreadsheet, FlaskConical, Play } from "lucide-react";
import type { LibraryItem } from "../api/types";
import { libraryItemHref, libraryItemKey } from "../hooks/useLibrarySelection";
import { Badge } from "./Chrome";
import { LibraryActions } from "./LibraryActions";
import styles from "./experiment-library.module.css";

const active = (status: string) => ["queued", "running", "cancelling"].includes(status);
export function LibraryFileRow({ item, folderName, selected, tabStop, disabled, editing, nameEditor, showDate, showFolder,
  select, toggle, focus, keyDown, open, rename, move, archive, finalFocus, dragStart, dragEnd, canDrag, archiveBlocked, register }: {
  item: LibraryItem; folderName: string; selected: boolean; tabStop: boolean; disabled: boolean;
  editing: boolean; nameEditor: ReactNode; showDate: boolean; showFolder: boolean; canDrag: boolean; archiveBlocked: boolean;
  select: (modifiers?: { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }) => void;
  toggle: (checked: boolean) => void; focus: () => void; keyDown: KeyboardEventHandler;
  open: () => void; rename: () => void; move: () => void; archive: () => void;
  finalFocus: () => HTMLElement | null; dragStart: DragEventHandler; dragEnd: DragEventHandler;
  register: (node: HTMLElement | null) => void;
}) {
  const row = useRef<HTMLDivElement | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [keyboardContext, setKeyboardContext] = useState(false);
  const prohibited = !item.archived && (archiveBlocked || item.kind === "run" && active(item.status));
  const statusText = item.status === "needs_mapping" ? "Needs mapping" : item.status === "ready_to_train" ? "Ready to train" : item.status.replaceAll("_", " ");
  const desktop = () => window.matchMedia("(min-width: 769px) and (hover: hover) and (pointer: fine)").matches;
  function click(event: MouseEvent) {
    if (disabled || editing || (event.target as HTMLElement).closest("button,input,[data-library-edit]")) return;
    if (desktop()) { select(event); row.current?.focus(); }
  }
  function menuItems(Item: typeof Menu.Item) {
    return <><Item onClick={open}>Open</Item><Item onClick={rename}>Rename</Item><Item onClick={move}>Move to folder</Item>
      <Menu.Separator /><Item disabled={prohibited} onClick={archive}>{item.archived ? "Restore" : "Archive"}</Item>
      {prohibited && <p className={styles.menuNote}>Available after the run finishes.</p>}</>;
  }
  return <ContextMenu.Root open={contextOpen} onOpenChange={setContextOpen} disabled={disabled || editing}>
    <ContextMenu.Trigger render={<article />} ref={node => { row.current = node; register(node); }} role="row"
      className={styles.row} aria-selected={selected} aria-label={item.display_name} tabIndex={tabStop ? 0 : -1}
      data-item-key={libraryItemKey(item)} data-selected={selected || undefined} data-editing={editing || undefined}
      onClick={click} onFocus={event => { if (event.target === event.currentTarget) focus(); }}
      onDoubleClick={event => { if (desktop() && !disabled && !editing && !(event.target as HTMLElement).closest("button,input,[data-library-edit]")) open(); }}
      onContextMenu={() => { setKeyboardContext(false); if (!selected && !disabled && !editing) select(); }}
      onKeyDown={event => {
        if ((event.target as HTMLElement).closest("button,input,[data-library-edit]")) return;
        if (!disabled && !editing && (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey))) {
          event.preventDefault(); if (!selected) select(); setKeyboardContext(true); setContextOpen(true);
        } else keyDown(event);
      }} draggable={canDrag} onDragStart={dragStart} onDragEnd={dragEnd}>
      <div role="gridcell"><label className={styles.check} onClick={event => event.stopPropagation()}><input type="checkbox" aria-label={`Select ${item.display_name}`} checked={selected} disabled={disabled} onChange={event => toggle(event.target.checked)} /></label></div>
      <div role="gridcell" className={styles.itemContent}>
        <span className={styles.fileIcon} aria-hidden="true">{item.kind === "upload" ? <FileSpreadsheet size={18} /> : <FlaskConical size={18} />}</span>
        <div className={styles.fileText}>
          <div className={styles.nameSlot} data-editing={editing || undefined}>
            <Link className={styles.itemLink} to={libraryItemHref(item)} draggable={false} tabIndex={editing ? -1 : 0} aria-hidden={editing || undefined}
              onClick={event => { if (disabled || editing || desktop() && event.detail > 0) event.preventDefault(); }}><strong>{item.display_name}</strong></Link>
            {nameEditor}
          </div>
          <div className={styles.meta}>{item.display_name !== item.original_name && <span>{item.original_name}</span>}
            <span>{item.kind === "upload" ? `${(item.row_count ?? 0).toLocaleString()} rows · ${item.run_count} ${item.run_count === 1 ? "run" : "runs"}` : item.source === "synthetic" ? "Sample" : "Upload"}</span>
            {showFolder && <span>{folderName}</span>}
          </div>
        </div>
      </div>
      <div role="gridcell" className={styles.kindCol}>{item.kind === "upload" ? "CSV" : "Run"}</div>
      <div role="gridcell" className={`${styles.rowStatus} ${styles.statusCol}`}><Badge tone={item.status === "completed" ? "ok" : ["failed", "timed_out", "interrupted"].includes(item.status) ? "bad" : active(item.status) ? "info" : "neutral"}>{item.status === "ready_to_train" ? <Play size={12} aria-hidden="true" /> : item.status === "completed" ? <Check size={12} aria-hidden="true" /> : null}{statusText}</Badge></div>
      {showDate && <div role="gridcell" className={styles.dateCol}>{item.created_at !== null ? <time dateTime={new Date(item.created_at * 1000).toISOString()}>{new Date(item.created_at * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</time> : "—"}</div>}
      <div role="gridcell" className={styles.rowActions}><LibraryActions label={`Actions for ${item.display_name}`} disabled={disabled || editing} finalFocus={finalFocus}>{() => menuItems(Menu.Item)}</LibraryActions></div>
    </ContextMenu.Trigger>
    <ContextMenu.Portal><ContextMenu.Positioner className={styles.layer} anchor={keyboardContext ? row : undefined}>
      <ContextMenu.Popup className={styles.menu} finalFocus={() => finalFocus() ?? row.current}>{menuItems(ContextMenu.Item)}</ContextMenu.Popup>
    </ContextMenu.Positioner></ContextMenu.Portal>
  </ContextMenu.Root>;
}
