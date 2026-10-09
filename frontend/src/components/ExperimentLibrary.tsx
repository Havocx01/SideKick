import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode, type KeyboardEvent } from "react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Dialog } from "@base-ui/react/dialog";
import { Menu } from "@base-ui/react/menu";
import { ContextMenu } from "@base-ui/react/context-menu";
import { Archive, Check, ChevronRight, FlaskConical, Folder, FolderOpen, FolderPlus, Inbox, Pencil, Search, Trash2, Upload, X } from "lucide-react";
import { api, ApiError, library } from "../api/client";
import type { LibraryFolder, LibraryItem, LibraryItemRef, LibrarySnapshot } from "../api/types";
import { useApi } from "../hooks/useApi";
import { Button, Select, StateBlock } from "./Chrome";
import { Expandable, ExpandableContent, ExpandableTrigger } from "./cult/Expandable";
import { FilterDropdown } from "./cult/FilterDropdown";
import { InlineLibraryName } from "./InlineLibraryName";
import { LibraryActions as Actions } from "./LibraryActions";
import { LibraryFileRow } from "./LibraryFileRow";
import { CsvAttachment } from "./CsvAttachment";
import { useLibrarySelection, libraryItemKey as key, libraryItemHref } from "../hooks/useLibrarySelection";
import { useLibraryDrag, type LibraryDropTarget } from "../hooks/useLibraryDrag";
import { csvValidationError, uploadCsv } from "../lib/csv-upload";
import styles from "./experiment-library.module.css";

type Editor = { mode: "create" } | { mode: "folderRename"; folder: LibraryFolder } | { mode: "folderRemove"; folder: LibraryFolder }
  | { mode: "rename"; item: LibraryItem } | { mode: "move"; items: LibraryItemRef[] };
type NameEditor = Extract<Editor, { mode: "create" | "folderRename" | "rename" }>;
type UploadState = { file: File; folderId: string | null; state: "uploading" | "error"; error?: string };
const isActive = (status: string) => ["queued", "running", "cancelling"].includes(status);
const errorText = (error: unknown) => error instanceof ApiError ? error.detail ?? error.message : error instanceof Error ? error.message : "Could not save. Try again.";
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

function FolderNavigationItem({ folder, active, count, saving, choose, edit, nameEditor, finalFocus, drop }: {
  folder: LibraryFolder; active: boolean; count: number; saving: boolean;
  choose: () => void; edit: (editor: Editor, trigger: HTMLElement | null) => void;
  nameEditor: ReactNode; finalFocus: () => HTMLElement | null; drop: ReturnType<ReturnType<typeof useLibraryDrag>["bindings"]>;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [keyboardContext, setKeyboardContext] = useState(false);
  return <ContextMenu.Root open={contextOpen} onOpenChange={setContextOpen} disabled={saving}>
    <ContextMenu.Trigger className={styles.folderRow} data-folder-id={folder.id} data-active={active || undefined} onContextMenu={() => setKeyboardContext(false)} {...drop}>
      {nameEditor ? <div className={styles.folderNameEdit}><Folder size={17} aria-hidden="true" /><div className={styles.nameSlot}><span className={styles.nameGhost} aria-hidden="true">{folder.name}</span>{nameEditor}</div></div> : <button ref={button} className={styles.folderButton} data-folder-open data-library-nav aria-current={active ? "page" : undefined} onClick={choose} disabled={saving}
        onKeyDown={event => { if (event.key === "F2" && !saving) { event.preventDefault(); edit({ mode: "folderRename", folder }, event.currentTarget); } else if (!saving && (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))) { event.preventDefault(); setKeyboardContext(true); setContextOpen(true); } }}>
        {active ? <FolderOpen size={17} aria-hidden="true" /> : <Folder size={17} aria-hidden="true" />}<span>{folder.name}</span><small className={styles.folderCount} aria-hidden="true">{count}</small>
      </button>}
      {!nameEditor && <Actions label={`Manage folder ${folder.name}`} disabled={saving} finalFocus={finalFocus}>{trigger => <>
        <Menu.Item onClick={() => edit({ mode: "folderRename", folder }, trigger())}><Pencil size={15} aria-hidden="true" />Rename folder</Menu.Item>
        <Menu.Item onClick={() => edit({ mode: "folderRemove", folder }, trigger())}><Trash2 size={15} aria-hidden="true" />Delete folder</Menu.Item>
      </>}</Actions>}
    </ContextMenu.Trigger>
    <ContextMenu.Portal><ContextMenu.Positioner className={styles.layer} anchor={keyboardContext ? button : undefined}><ContextMenu.Popup className={styles.menu} finalFocus={() => finalFocus() ?? button.current}>
      <ContextMenu.Item onClick={() => edit({ mode: "folderRename", folder }, button.current)}><Pencil size={15} aria-hidden="true" />Rename folder</ContextMenu.Item>
      <ContextMenu.Item onClick={() => edit({ mode: "folderRemove", folder }, button.current)}><Trash2 size={15} aria-hidden="true" />Delete folder</ContextMenu.Item>
    </ContextMenu.Popup></ContextMenu.Positioner></ContextMenu.Portal>
  </ContextMenu.Root>;
}

export function ExperimentLibrary() {
  const tabLayoutId = useId();
  const reducedMotion = useReducedMotion();
  const health = useApi(() => api.health(), []);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const currentParams = useRef(params);
  useEffect(() => { currentParams.current = params; if (!mutating.current) setNameEditor(null); }, [params]);
  const [data, setData] = useState<LibrarySnapshot | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [nameEditor, setNameEditor] = useState<NameEditor | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [destination, setDestination] = useState("unfiled");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [message, setMessage] = useState("");
  const alive = useRef(false);
  const revision = useRef(0);
  const mutating = useRef(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const rowNodes = useRef(new Map<string, HTMLElement>());
  const browserPaused = useRef(false);
  const isDesktop = () => window.matchMedia("(min-width: 769px) and (hover: hover) and (pointer: fine)").matches;
  const [desktop, setDesktop] = useState(isDesktop);
  const busy = saving || upload?.state === "uploading";
  const tab = params.get("tab") === "uploads" ? "uploads" : params.get("tab") === "runs" ? "runs" : "all";
  const view = params.get("view") === "archive" ? "archive" : params.get("view") === "unfiled" ? "unfiled" : "all";
  const folderId = params.get("folder");
  const folder = data?.folders.find(value => value.id === folderId);
  const missingFolder = Boolean(data && folderId && !folder);
  const search = params.get("q") ?? "";
  const source = params.get("source") ?? "all";
  const status = params.get("status") ?? "all";
  const sort = params.get("sort") ?? "newest";
  const folders = data?.folders ?? [];
  const byDate = view === "all" && !folderId;
  const [today, setToday] = useState(() => dateKey(new Date()));
  const [expansion, setExpansion] = useState<{ scope: string; days: Record<string, boolean> }>({ scope: "", days: {} });
  const groupScope = [tab, view, folderId, search, source, status, today].join("\0");
  useEffect(() => {
    const media = window.matchMedia("(min-width: 769px) and (hover: hover) and (pointer: fine)");
    const change = () => setDesktop(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => () => uploadController.current?.abort(), []);
  useEffect(() => {
    const timer = window.setInterval(() => setToday(dateKey(new Date())), 30000);
    const update = () => setToday(dateKey(new Date()));
    window.addEventListener("focus", update);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", update); };
  }, []);

  const refresh = useCallback(async (force = false) => {
    const version = ++revision.current;
    try {
      const next = await library.get();
      if (alive.current && revision.current === version && (force || !browserPaused.current)) { setData(next); setLoadError(null); }
    } catch (error) {
      if (alive.current && revision.current === version) setLoadError(error as Error);
      throw error;
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    let pending = false;
    const update = async () => {
      if (pending || mutating.current || browserPaused.current || uploadController.current) return;
      pending = true;
      try { await refresh(); } catch { /* Keep previous rows visible and offer retry. */ }
      finally { pending = false; }
    };
    void update();
    const timer = window.setInterval(update, 3000);
    return () => { alive.current = false; revision.current++; window.clearInterval(timer); };
  }, [refresh]);

  function query(changes: Record<string, string | null>, replace = false) {
    if (busy) return;
    setNameEditor(null);
    const next = new URLSearchParams(currentParams.current);
    for (const [key, value] of Object.entries(changes)) value && value !== "all" ? next.set(key, value) : next.delete(key);
    currentParams.current = next;
    setParams(next, { replace });
    fileSelection.clear(); setActionError(""); setMessage("");
  }
  function chooseView(value: string) {
    query(value.startsWith("folder:") ? { folder: value.slice(7), view: null } : { folder: null, view: value, ...(value === "all" ? { sort: null } : {}) });
  }
  const items = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (data?.items ?? []).filter(item => (tab === "all" || item.kind === (tab === "runs" ? "run" : "upload"))
      && item.archived === (view === "archive")
      && (!folderId || item.folder_id === folderId)
      && (view !== "unfiled" || !item.folder_id)
      && (source === "all" || item.source === source)
      && (status === "all" || item.status === status)
      && (!needle || [item.display_name, item.original_name, item.id, item.dataset_id].some(value => value.toLocaleLowerCase().includes(needle))))
      .sort((a, b) => !byDate && sort === "name" ? a.display_name.localeCompare(b.display_name) : !byDate && sort === "oldest"
        ? (a.created_at ?? Infinity) - (b.created_at ?? Infinity) : (b.created_at ?? -Infinity) - (a.created_at ?? -Infinity));
  }, [data, tab, view, folderId, source, status, search, sort, byDate]);
  const hasFilters = Boolean(search.trim() || source !== "all" || status !== "all");
  const dateGroups = useMemo(() => {
    const groups = new Map<string, { date: Date | null; items: LibraryItem[] }>();
    for (const item of items) {
      const date = item.created_at === null ? null : new Date(item.created_at * 1000);
      const day = date ? dateKey(date) : "unknown";
      if (!groups.has(day)) groups.set(day, { date, items: [] });
      groups.get(day)!.items.push(item);
    }
    return Array.from(groups, ([day, group]) => ({ day, ...group }));
  }, [items]);
  const isDayOpen = (day: string) => (expansion.scope === groupScope ? expansion.days[day] : undefined) ?? (day === today || hasFilters);
  const visibleItems = byDate ? dateGroups.filter(group => isDayOpen(group.day)).flatMap(group => group.items) : items;
  const fileSelection = useLibrarySelection(visibleItems, groupScope, setMessage);
  const { selected, selection } = fileSelection;
  const selectedRefs = selection.map(({ kind, id }) => ({ kind, id }));
  const hasActive = selection.some(item => item.kind === "run" && isActive(item.status));
  const countForView = (value: string) => (data?.items ?? []).filter(item => (tab === "all" || item.kind === (tab === "runs" ? "run" : "upload"))
    && (value === "archive" ? item.archived : !item.archived)
    && (value === "unfiled" ? !item.folder_id : value.startsWith("folder:") ? item.folder_id === value.slice(7) : true)).length;
  const itemWord = (count: number) => count === 1 ? "item" : "items";
  const setupLink = (kind: "sample" | "upload") => `/new?source=${kind}${folder ? `&folder=${folder.id}` : ""}`;
  const viewLabel = view === "archive" ? "Archive" : folder?.name ?? (view === "unfiled" ? "Unfiled" : "All items");
  const currentView = folderId ? `folder:${folderId}` : view;
  const emptyTitle = hasFilters ? "No matching items" : view === "archive" ? "Archive is empty"
    : !data?.items.length ? "No experiments yet" : folder ? "This folder is empty"
    : view === "unfiled" ? "Nothing unfiled" : tab !== "all" ? `No ${tab} here` : "This view is empty";
  const emptyDescription = hasFilters ? "Try another name or clear your filters."
    : view === "archive" ? "Archived runs and CSVs stay here until you restore them."
    : folder ? "Drop a CSV here, or move runs into this folder."
    : view === "unfiled" ? "Items without a folder appear here."
    : "Create a folder, run a sample, or upload equipment histories.";

  function openEditor(next: Editor, trigger: HTMLElement | null) {
    if (busy) return;
    returnFocus.current = trigger;
    setActionError(""); setMessage("");
    if (next.mode === "create" || next.mode === "folderRename" || next.mode === "rename") {
      browserPaused.current = true;
      setNameEditor(next);
      return;
    }
    setNameEditor(null); setEditor(next);
    setDestination(folderId ?? "unfiled");
  }
  async function save(operation: () => Promise<unknown>, confirmation: string) {
    if (mutating.current) throw new Error("Wait for the current save to finish.");
    mutating.current = true; revision.current++; setSaving(true); setActionError(""); setMessage("");
    try {
      await operation();
      if (!alive.current) return;
      setMessage(confirmation);
      try { await refresh(true); } catch { /* A failed refresh must not report the successful save as failed. */ }
    } catch (error) { throw new Error(errorText(error)); }
    finally { mutating.current = false; if (alive.current) setSaving(false); }
  }
  async function mutate(operation: () => Promise<unknown>, confirmation: string) {
    try { await save(operation, confirmation); if (alive.current) { setEditor(null); fileSelection.clear(); } }
    catch (error) { if (alive.current) setActionError(errorText(error)); }
  }
  function submit() {
    if (!editor) return;
    if (editor.mode === "folderRemove") return mutate(async () => {
      await library.removeFolder(editor.folder.id);
      if (folderId === editor.folder.id) {
        const next = new URLSearchParams(currentParams.current); next.delete("folder"); next.set("view", "unfiled");
        currentParams.current = next; setParams(next);
      }
    }, "Folder removed. Its items are now Unfiled.");
    if (editor.mode === "move") return mutate(() => library.update({ items: editor.items, action: "move", folder_id: destination === "unfiled" ? null : destination }), "Items moved.");
  }
  function archive(items: LibraryItemRef[], restore = false) {
    void mutate(() => library.update({ items, action: restore ? "restore" : "archive" }), restore ? "Items restored." : "Items archived. Find them in Archive.");
  }
  function finishName(focus: boolean, target: NameEditor) {
    if (!alive.current) return;
    browserPaused.current = false; setNameEditor(null);
    if (focus) requestAnimationFrame(() => {
      const node = target.mode === "rename" ? rowNodes.current.get(key(target.item)) : target.mode === "folderRename"
        ? document.querySelector<HTMLElement>(`[data-folder-id="${target.folder.id}"] [data-folder-open]`) : returnFocus.current;
      (node?.isConnected ? node : heading.current)?.focus();
    });
    void refresh().catch(() => {});
  }
  function inlineEditor(target: NameEditor) {
    return <InlineLibraryName key={target.mode === "rename" ? key(target.item) : target.mode === "folderRename" ? target.folder.id : "new-folder"}
      name={target.mode === "rename" ? target.item.display_name : target.mode === "folderRename" ? target.folder.name : ""}
      label={target.mode === "rename" ? "Display name" : "Folder name"} maxLength={target.mode === "rename" ? 120 : 80} inputRef={nameInput}
      done={focus => finishName(focus, target)} save={value => target.mode === "create" ? save(() => library.createFolder(value), "Folder created.")
        : target.mode === "folderRename" ? save(() => library.renameFolder(target.folder.id, value), "Folder renamed.")
        : save(() => library.update({ items: [{ kind: target.item.kind, id: target.item.id }], action: "rename", display_name: value }), "Name saved.")} />;
  }
  async function uploadFile(file: File, targetFolder: string | null) {
    if (mutating.current || uploadController.current) return;
    const invalid = csvValidationError(file);
    if (invalid) { setUpload({ file, folderId: targetFolder, state: "error", error: invalid }); return; }
    const controller = new AbortController(); uploadController.current = controller;
    setActionError(""); setMessage(""); setUpload({ file, folderId: targetFolder, state: "uploading" });
    try {
      const dataset = await uploadCsv(file, controller.signal, targetFolder);
      if (alive.current && !controller.signal.aborted) navigate(`/new?source=upload&dataset=${dataset.dataset_id}${targetFolder ? `&folder=${targetFolder}` : ""}`);
    } catch (error) {
      if (alive.current && !controller.signal.aborted) setUpload({ file, folderId: targetFolder, state: "error", error: errorText(error) });
    } finally { if (uploadController.current === controller) uploadController.current = null; }
  }
  function cancelUpload() {
    uploadController.current?.abort(); uploadController.current = null; setUpload(null);
    void refresh().catch(() => {});
  }
  const drag = useLibraryDrag({ blocked: Boolean(busy || nameEditor || editor), uploadAllowed: Boolean(health.data?.can_upload),
    reject: setActionError,
    finish: () => { browserPaused.current = Boolean(nameEditor); if (!mutating.current) void refresh().catch(() => {}); },
    move: (batch, target) => {
      const entries = batch.filter(item => target.archive || item.folder_id !== target.folderId);
      if (!entries.length) { void refresh().catch(() => {}); return; }
      const refs = entries.map(({ kind, id }) => ({ kind, id }));
      void mutate(() => library.update({ items: refs, action: target.archive ? "archive" : "move", ...(target.archive ? {} : { folder_id: target.folderId ?? null }) }), target.archive ? "Items archived. Find them in Archive." : `Moved to ${target.name}.`);
    },
    upload: (files, target) => {
      if (files.length !== 1) { setActionError("Drop one CSV file at a time."); return; }
      if (files[0]) void uploadFile(files[0], target.folderId ?? null);
    },
  });
  browserPaused.current = drag.paused.current || Boolean(nameEditor);
  const folderTarget = (id: string | null, name: string): LibraryDropTarget => ({ key: id ? `folder:${id}` : "unfiled", name, folderId: id, items: true, files: true });
  const archiveTarget: LibraryDropTarget = { key: "archive", name: "Archive", archive: true, items: true, files: false };
  const contentTarget: LibraryDropTarget = view === "archive" ? archiveTarget : { ...folderTarget(folderId, folder?.name ?? "Unfiled"), key: "content", items: Boolean(folder || view === "unfiled"), files: !missingFolder };
  function rowKeyDown(event: KeyboardEvent, item: LibraryItem) {
    if (busy || nameEditor) return;
    if (event.key === "F2") { event.preventDefault(); openEditor({ mode: "rename", item }, rowNodes.current.get(key(item)) ?? null); }
    else if (event.key === "Enter") { event.preventDefault(); navigate(libraryItemHref(item)); }
    else if (event.key === "Escape") { event.preventDefault(); fileSelection.clear(); }
    else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") { event.preventDefault(); fileSelection.selectAll(); }
    else if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const index = visibleItems.findIndex(value => key(value) === key(item));
      const next = event.key === "Home" ? 0 : event.key === "End" ? visibleItems.length - 1 : Math.max(0, Math.min(visibleItems.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
      const destination = visibleItems[next];
      if (destination) { if (event.ctrlKey || event.metaKey) fileSelection.setFocused(key(destination)); else fileSelection.select(destination, { shiftKey: event.shiftKey }); rowNodes.current.get(key(destination))?.focus(); }
    }
  }
  function rows(entries: LibraryItem[]) {
    return entries.map(item => <LibraryFileRow key={key(item)} item={item} folderName={folders.find(value => value.id === item.folder_id)?.name ?? "Unfiled"}
      selected={selected.includes(key(item))} tabStop={fileSelection.focused === key(item) || (!fileSelection.focused && visibleItems[0] === item)}
      disabled={Boolean(busy || (nameEditor && !(nameEditor.mode === "rename" && key(nameEditor.item) === key(item))))} editing={nameEditor?.mode === "rename" && key(nameEditor.item) === key(item)}
      nameEditor={nameEditor?.mode === "rename" && key(nameEditor.item) === key(item) ? inlineEditor(nameEditor) : null}       showDate showFolder={byDate}
      select={modifiers => fileSelection.select(item, modifiers)} toggle={checked => fileSelection.toggle(item, checked)} focus={() => fileSelection.setFocused(key(item))}
      keyDown={event => rowKeyDown(event, item)} open={() => navigate(libraryItemHref(item))}
      rename={() => openEditor({ mode: "rename", item }, rowNodes.current.get(key(item)) ?? null)}
      move={() => openEditor({ mode: "move", items: selected.includes(key(item)) ? selectedRefs : [{ kind: item.kind, id: item.id }] }, rowNodes.current.get(key(item)) ?? null)}
      archive={() => archive(selected.includes(key(item)) ? selectedRefs : [{ kind: item.kind, id: item.id }], item.archived)}
      archiveBlocked={selected.includes(key(item)) && hasActive}
      finalFocus={() => nameInput.current ?? rowNodes.current.get(key(item)) ?? null} canDrag={Boolean(desktop && !busy && !nameEditor && !editor && !item.archived)}
      dragStart={event => { drag.start(event, item, selection, () => fileSelection.select(item)); browserPaused.current = drag.paused.current; }} dragEnd={() => drag.stop()}
      register={node => { if (node) rowNodes.current.set(key(item), node); else rowNodes.current.delete(key(item)); }} />);
  }
  const editorTitle = editor?.mode === "folderRemove" ? "Delete folder" : "Move to folder";

  return <div className={styles.library} data-dragging={drag.dragging || undefined}>
    <header className={styles.header}><div><h1 ref={heading} tabIndex={-1}>Experiments</h1>
      <nav className={styles.crumb} aria-label="Folder path"><button type="button" disabled={busy || currentView === "all"} onClick={() => chooseView("all")}>Library</button>{currentView !== "all" && <><ChevronRight size={14} aria-hidden="true" /><span>{viewLabel}</span></>}</nav>
    </div>
      <div className={styles.headerActions}>
        <Link className={styles.headerAction} data-library-nav aria-disabled={busy || undefined} onClick={event => { if (busy) event.preventDefault(); }} to={setupLink("sample")}><FlaskConical size={16} aria-hidden="true" />Run sample</Link>
        {health.data?.can_upload && <Link className={`${styles.headerAction} ${styles.primaryAction}`} data-library-nav aria-disabled={busy || undefined} onClick={event => { if (busy) event.preventDefault(); }} to={setupLink("upload")}><Upload size={16} aria-hidden="true" />Upload CSV</Link>}
      </div>
    </header>
    <div className={styles.layout}>
      <aside className={styles.sidebar} aria-label="Experiment folders">
        <nav className={styles.folderNav} aria-label="Library views">
          <p className={styles.navLabel}>Library</p>
          {([["all", "All items", Inbox], ["unfiled", "Unfiled", Folder]] as const).map(([value, label, ViewIcon]) =>
            <button key={value} className={styles.folderButton} data-library-nav disabled={busy} {...(value === "unfiled" ? drag.bindings(folderTarget(null, "Unfiled")) : {})} aria-current={currentView === value ? "page" : undefined} onClick={() => chooseView(value)}><ViewIcon size={17} aria-hidden="true" /><span>{label}</span><small className={styles.folderCount} aria-hidden="true">{countForView(value)}</small></button>)}
          <div className={styles.folderHead}><p className={styles.navLabel}>Folders</p><Button variant="ghost" className={styles.iconButton} aria-label="New folder" disabled={busy || Boolean(nameEditor)} onClick={event => openEditor({ mode: "create" }, event.currentTarget)}><FolderPlus size={18} aria-hidden="true" /></Button></div>
          <div className={styles.customFolders}>
            {desktop && nameEditor?.mode === "create" && <div className={styles.folderNameEdit}><Folder size={17} aria-hidden="true" />{inlineEditor(nameEditor)}</div>}
            {folders.map(value => <FolderNavigationItem key={value.id} folder={value} active={folderId === value.id} count={countForView(`folder:${value.id}`)} saving={Boolean(busy || (nameEditor && !(nameEditor.mode === "folderRename" && nameEditor.folder.id === value.id)))} choose={() => chooseView(`folder:${value.id}`)} edit={openEditor}
              nameEditor={desktop && nameEditor?.mode === "folderRename" && nameEditor.folder.id === value.id ? inlineEditor(nameEditor) : null}
              finalFocus={() => nameInput.current} drop={drag.bindings(folderTarget(value.id, value.name))} />)}
            {!folders.length && nameEditor?.mode !== "create" && <p className={styles.folderHint}>New folder groups related runs and CSVs.</p>}
          </div>
          <button className={`${styles.folderButton} ${styles.archiveButton}`} data-library-nav disabled={busy} {...drag.bindings(archiveTarget)} aria-current={currentView === "archive" ? "page" : undefined} onClick={() => chooseView("archive")}><Archive size={17} aria-hidden="true" /><span>Archive</span><small className={styles.folderCount} aria-hidden="true">{countForView("archive")}</small></button>
        </nav>
      </aside>
      <div className={styles.controls}>
        <span className="sr-only" aria-live="polite">{drag.feedback}</span>
        <div className={styles.mobileFolders} data-library-nav><Select label="Folder" value={currentView} disabled={Boolean(busy)} options={[{ value: "all", label: "All items" }, { value: "unfiled", label: "Unfiled" }, ...folders.map(value => ({ value: `folder:${value.id}`, label: value.name })), { value: "archive", label: "Archive" }, ...(missingFolder ? [{ value: `folder:${folderId}`, label: "Unavailable folder" }] : [])]} onValueChange={chooseView} />
          <Button variant="secondary" aria-label="New folder" disabled={busy || Boolean(nameEditor)} onClick={event => openEditor({ mode: "create" }, event.currentTarget)}><FolderPlus size={18} aria-hidden="true" /></Button>
          {folder && <Actions label={`Manage folder ${folder.name}`} disabled={busy || Boolean(nameEditor)} finalFocus={() => nameInput.current}>{trigger => <><Menu.Item onClick={() => openEditor({ mode: "folderRename", folder }, trigger())}><Pencil size={15} aria-hidden="true" />Rename folder</Menu.Item><Menu.Item onClick={() => openEditor({ mode: "folderRemove", folder }, trigger())}><Trash2 size={15} aria-hidden="true" />Delete folder</Menu.Item></>}</Actions>}
        </div>
        {!desktop && nameEditor?.mode === "create" && <div className={styles.mobileNameEdit}><FolderPlus size={17} aria-hidden="true" />{inlineEditor(nameEditor)}</div>}
        <div className={styles.sectionHead}><div className={styles.nameSlot}><h2 className={!desktop && nameEditor?.mode === "folderRename" ? styles.nameGhost : undefined} aria-hidden={!desktop && nameEditor?.mode === "folderRename" || undefined}>{viewLabel}</h2>{!desktop && nameEditor?.mode === "folderRename" && inlineEditor(nameEditor)}</div><span>{items.length} {itemWord(items.length)}</span></div>
        <div className={styles.toolbar}>
          <LayoutGroup id={tabLayoutId}><div className={styles.tabs} role="tablist" aria-label="Item type" data-library-nav>{([["all", "All"], ["runs", "Runs"], ["uploads", "CSVs"]] as const).map(([value, label]) => <button key={value} id={`library-${value}-tab`} role="tab" disabled={busy} aria-selected={tab === value} aria-controls="library-items" tabIndex={tab === value ? 0 : -1} onClick={() => query({ tab: value === "all" ? null : value, status: null, source: null })} onKeyDown={event => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); const order = ["all", "runs", "uploads"] as const; const index = Math.max(0, order.indexOf(tab)); const next = event.key === "Home" ? "all" : event.key === "End" ? "uploads" : order[Math.max(0, Math.min(2, index + (event.key === "ArrowRight" ? 1 : -1)))] ?? "all"; query({ tab: next === "all" ? null : next, status: null, source: null }); document.getElementById(`library-${next}-tab`)?.focus(); } }}>{tab === value && <motion.span aria-hidden="true" className={styles.tabIndicator} layoutId="active-library-tab" initial={false} transition={{ duration: reducedMotion ? 0 : motionTokens.duration.fast, ease: motionTokens.ease.enter }} />}<span className={styles.tabLabel}>{label}</span></button>)}</div></LayoutGroup>
          <label className={styles.search} data-library-nav><Search size={17} aria-hidden="true" /><span className="sr-only">Search this folder</span><input type="search" disabled={busy} value={search} placeholder="Search this folder" onChange={event => query({ q: event.target.value }, true)} />{search && <button type="button" className={styles.clearSearch} aria-label="Clear search" disabled={busy} onClick={event => { event.preventDefault(); event.currentTarget.parentElement?.querySelector("input")?.focus(); query({ q: null }); }}><X size={15} aria-hidden="true" /></button>}</label>
          <FilterDropdown disabled={Boolean(busy)} activeCount={Number(source !== "all") + Number(status !== "all")} onClear={() => query({ source: null, status: null })} groups={[
            ...(tab !== "uploads" ? [{ label: "Data source", value: source, onValueChange: (value: string) => query({ source: value }), options: [{ value: "all", label: "All sources" }, { value: "upload", label: "Uploaded data" }, { value: "synthetic", label: "Synthetic sample" }] }] : []),
            { label: "Status", value: status, onValueChange: (value: string) => query({ status: value }), options: [{ value: "all", label: "All statuses" }, ...(tab !== "runs" ? [{ value: "needs_mapping", label: "Needs mapping" }, { value: "ready_to_train", label: "Ready to train" }] : []), ...(tab !== "uploads" ? ["queued", "running", "cancelling", "completed", "failed", "cancelled", "timed_out", "interrupted"].map(value => ({ value, label: value.charAt(0).toUpperCase() + value.slice(1).replaceAll("_", " ") })) : [])] },
            ...(!byDate ? [{ label: "Sort by", value: sort, onValueChange: (value: string) => query({ sort: value }), options: [{ value: "newest", label: "Newest first" }, { value: "oldest", label: "Oldest first" }, { value: "name", label: "Name" }] }] : []),
          ]} />
        </div>
        <div className={styles.feedback} aria-live="polite">{message && <span role="status"><Check size={15} aria-hidden="true" />{message}</span>}{actionError && !editor && <span role="alert">{actionError}</span>}</div>
      </div>
      <section className={styles.main} aria-label="Experiment library">
        <span className="sr-only" aria-live="polite">{selection.length ? `${selection.length} items selected.` : "No items selected."}</span>
        {upload && <div className={styles.uploadAttachment}><CsvAttachment name={upload.file.name} size={upload.file.size} state={upload.state} error={upload.error} onRemove={cancelUpload} onRetry={() => { void uploadFile(upload.file, upload.folderId); }} /></div>}
        {loadError && data && <div className={styles.error} role="alert"><p>Could not refresh the library. Your last loaded items are still here.</p><Button variant="secondary" onClick={() => { void refresh().catch(() => {}); }}>Retry loading</Button></div>}
        {missingFolder && <div className={styles.error} role="status"><p>This folder is unavailable. Your items are still in the library.</p><Button variant="secondary" onClick={() => query({ folder: null, view: null })}>Show all items</Button></div>}
        <StateBlock loading={!data && !loadError} error={!data ? loadError : null}>
          <div id="library-items" role="tabpanel" aria-labelledby={`library-${tab}-tab`} {...drag.bindings(contentTarget)}>
            <p className="sr-only" id="library-keyboard-help">Click to select. Double-click or press Enter to open. F2 renames. Control or Command toggles selection; Shift selects a range. Drag selected items onto a folder to move them.</p>
            {items.length && !missingFolder ? <div className={styles.list}>
              <div className={styles.listHead} role="row">
                <label className={styles.selectAll}><input type="checkbox" aria-label="Select visible items" disabled={busy || Boolean(nameEditor) || !visibleItems.length} checked={visibleItems.length > 0 && visibleItems.slice(0, 100).every(item => selected.includes(key(item)))} ref={node => { if (node) node.indeterminate = selection.length > 0 && !visibleItems.slice(0, 100).every(item => selected.includes(key(item))); }} onChange={event => fileSelection.selectAll(event.target.checked)} /></label>
                <span>Name</span><span className={styles.kindCol}>Kind</span><span className={styles.statusCol}>Status</span><span className={styles.dateCol}>Modified</span><span className={styles.rowActions} aria-hidden="true" />
              </div>
              <div role="grid" aria-label={folder ? `Items in ${folder.name}` : viewLabel} aria-multiselectable="true" aria-describedby="library-keyboard-help">
              {byDate ? dateGroups.map(group => <Expandable key={group.day} className={styles.dateGroup} expanded={isDayOpen(group.day)} onToggle={() => setExpansion(current => ({ scope: groupScope, days: { ...(current.scope === groupScope ? current.days : {}), [group.day]: !isDayOpen(group.day) } }))}>
                  <ExpandableTrigger className={styles.dateHeading} disabled={Boolean(busy || nameEditor || drag.dragging)}><ChevronRight size={16} aria-hidden="true" /><span>{group.day === today ? "Today" : group.date ? group.date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "Date unavailable"}</span><small>{group.items.length} {itemWord(group.items.length)}</small></ExpandableTrigger>
                  <ExpandableContent>{rows(group.items)}</ExpandableContent>
                </Expandable>) : rows(items)
              }
              </div>
            </div> : !missingFolder && <div className={styles.empty}><FolderOpen size={28} aria-hidden="true" /><h3>{emptyTitle}</h3><p>{emptyDescription}</p>{hasFilters ? <Button variant="secondary" onClick={() => query({ q: null, status: null, source: null })}>Clear filters</Button> : view !== "archive" && <Link className="button" to={setupLink(health.data?.can_upload ? "upload" : "sample")}>{health.data?.can_upload ? "Upload CSV" : "Run sample"}</Link>}</div>}
          </div>
        </StateBlock>
        {selection.length > 0 && <div className={styles.bulk} aria-label="Selected item actions"><strong>{selection.length} selected</strong><Button variant="secondary" disabled={busy || Boolean(nameEditor)} onClick={event => openEditor({ mode: "move", items: selectedRefs }, event.currentTarget)}>Move to folder</Button><Button variant="secondary" disabled={busy || Boolean(nameEditor) || (view !== "archive" && hasActive)} onClick={() => archive(selectedRefs, view === "archive")}>{view === "archive" ? "Restore selected" : "Archive selected"}</Button><Button variant="ghost" aria-label="Clear selection" disabled={busy} onClick={fileSelection.clear}><X size={16} aria-hidden="true" /></Button>{hasActive && view !== "archive" && <p>Active runs must finish before archiving.</p>}{selection.length === 100 && <p>Select up to 100 items at a time.</p>}</div>}
      </section>
    </div>
    <Dialog.Root open={Boolean(editor)} onOpenChange={open => { if (!open && !saving) { setEditor(null); setActionError(""); } }} disablePointerDismissal={saving}>
      <Dialog.Portal><Dialog.Backdrop className={styles.backdrop} /><Dialog.Popup className={styles.dialog} finalFocus={() => returnFocus.current?.isConnected ? returnFocus.current : heading.current}>
        <header><Dialog.Title>{editorTitle}</Dialog.Title><Dialog.Close className={styles.iconButton} aria-label="Close folder editor" disabled={saving}><X size={18} aria-hidden="true" /></Dialog.Close></header>
        <form onSubmit={event => { event.preventDefault(); void submit(); }}>
          <Dialog.Description>{editor?.mode === "folderRemove" ? `Delete “${editor.folder.name}”? Its items move to Unfiled. Data and results are retained.` : editor?.mode === "move" ? `Choose a folder for ${editor.items.length === 1 ? "this item" : `${editor.items.length} items`}.` : ""}</Dialog.Description>
          {editor?.mode === "move" && <Select label="Destination folder" value={destination} onValueChange={setDestination} disabled={saving} options={[{ value: "unfiled", label: "Unfiled" }, ...folders.map(value => ({ value: value.id, label: value.name }))]} />}
          {actionError && <p className={styles.dialogError} role="alert">{actionError}</p>}
          <footer><Dialog.Close render={<Button variant="secondary" />} disabled={saving}>Cancel</Dialog.Close><Button type="submit" loading={saving} disabled={saving}>{editor?.mode === "folderRemove" ? "Delete folder" : "Move items"}</Button></footer>
        </form>
      </Dialog.Popup></Dialog.Portal>
    </Dialog.Root>
  </div>;
}
