import { useEffect, useRef, useState, type DragEvent } from "react";
import type { LibraryItem } from "../api/types";
import styles from "../components/experiment-library.module.css";

const dragType = "application/x-sidekick-library-items";
export type LibraryDropTarget = { key: string; name: string; folderId?: string | null; archive?: boolean; items: boolean; files: boolean };
const hasFiles = (transfer: DataTransfer) => Array.from(transfer.types).includes("Files");

export function useLibraryDrag({ blocked, uploadAllowed, move, upload, finish, reject }: {
  blocked: boolean; uploadAllowed: boolean;
  move: (items: LibraryItem[], target: LibraryDropTarget) => void;
  upload: (files: File[], target: LibraryDropTarget) => void;
  finish: () => void;
  reject: (message: string) => void;
}) {
  const captured = useRef<LibraryItem[] | null>(null);
  const paused = useRef(false);
  const fileDepth = useRef(0);
  const onFinish = useRef(finish);
  const hovered = useRef<string | null>(null);
  const preview = useRef<HTMLElement | null>(null);
  onFinish.current = finish;
  const [dragging, setDragging] = useState(false);
  const [targetKey, setTargetKey] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  useEffect(() => {
    // Files dropped outside a valid zone must not replace the current app page.
    const preventFileNavigation = (event: globalThis.DragEvent) => {
      if (event.dataTransfer && hasFiles(event.dataTransfer)) {
        event.preventDefault();
        if (event.type === "dragover") {
          beginFiles();
          if (!(event.target as HTMLElement)?.closest?.("[data-library-drop]")) event.dataTransfer.dropEffect = "none";
        } else stop();
      }
    };
    const enter = (event: globalThis.DragEvent) => {
      if (event.dataTransfer && hasFiles(event.dataTransfer)) { fileDepth.current++; beginFiles(); }
    };
    const leave = (event: globalThis.DragEvent) => {
      if (event.dataTransfer && hasFiles(event.dataTransfer)) {
        fileDepth.current = Math.max(0, fileDepth.current - 1);
        if (!fileDepth.current) stop();
      }
    };
    // Track every nested file boundary, even when a drop zone stops bubbling.
    window.addEventListener("dragenter", enter, true);
    window.addEventListener("dragleave", leave, true);
    window.addEventListener("dragover", preventFileNavigation);
    window.addEventListener("drop", preventFileNavigation);
    const end = () => stop();
    window.addEventListener("dragend", end);
    return () => {
      window.removeEventListener("dragenter", enter, true);
      window.removeEventListener("dragleave", leave, true);
      window.removeEventListener("dragover", preventFileNavigation);
      window.removeEventListener("drop", preventFileNavigation);
      window.removeEventListener("dragend", end);
      preview.current?.remove();
    };
  }, []);
  function beginFiles() {
    if (!paused.current) { paused.current = true; fileDepth.current = Math.max(1, fileDepth.current); setDragging(true); }
  }
  function stop(refresh = true) {
    const hadDrag = paused.current;
    captured.current = null; paused.current = false; fileDepth.current = 0;
    hovered.current = null; preview.current?.remove(); preview.current = null;
    setDragging(false); setTargetKey(null); setFeedback("");
    if (hadDrag && refresh) onFinish.current();
  }
  function start(event: DragEvent, item: LibraryItem, selection: LibraryItem[], select: () => void) {
    if (blocked || item.archived || !window.matchMedia("(hover: hover) and (pointer: fine)").matches
      || (event.target as HTMLElement).closest("button,input,[data-library-edit]")) { event.preventDefault(); return; }
    const batch = selection.some(value => value.kind === item.kind && value.id === item.id) ? selection : [item];
    if (batch.some(value => value.archived)) { event.preventDefault(); return; }
    if (batch.length === 1) select();
    captured.current = [...batch]; paused.current = true; setDragging(true);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(dragType, JSON.stringify(batch.map(({ kind, id }) => ({ kind, id }))));
    const ghost = document.createElement("div");
    ghost.className = styles.dragPreview ?? "";
    ghost.textContent = batch.length === 1 ? batch[0]!.display_name : `${batch.length} items`;
    document.body.appendChild(ghost);
    preview.current = ghost;
    event.dataTransfer.setDragImage(ghost, 12, 12);
    setTimeout(() => { ghost.remove(); if (preview.current === ghost) preview.current = null; }, 0);
    setFeedback("Drop on a folder to move.");
  }
  function valid(target: LibraryDropTarget, files: boolean) {
    if (blocked) return false;
    if (files) return uploadAllowed && target.files;
    if (!captured.current || !target.items) return false;
    return !target.archive || !captured.current.some(item => item.kind === "run" && ["queued", "running", "cancelling"].includes(item.status));
  }
  function bindings(target: LibraryDropTarget) {
    function hover(event: DragEvent<HTMLElement>) {
      const files = hasFiles(event.dataTransfer);
      if (!files && !(captured.current && event.dataTransfer.types.includes(dragType))) return;
      if (files) beginFiles();
      event.preventDefault(); event.stopPropagation();
      const allowed = valid(target, files);
      event.dataTransfer.dropEffect = allowed ? files ? "copy" : "move" : "none";
      hovered.current = target.key;
      setTargetKey(allowed ? target.key : null);
      setFeedback(allowed ? files ? `Upload CSV to ${target.name}.` : target.archive ? "Move to Archive." : `Move to ${target.name}.`
        : blocked ? "Finish the current edit or save first." : files ? "CSV uploads are unavailable here." : target.archive ? "Active runs must finish before archiving." : "Choose a folder or Unfiled to move items.");
    }
    return {
      "data-library-drop": target.key,
      "data-drop-active": targetKey === target.key || undefined,
      onDragEnter: hover,
      onDragOver: hover,
      onDragLeave(event: DragEvent<HTMLElement>) {
        if (hovered.current !== target.key) return;
        const related = event.relatedTarget;
        if (related instanceof Node && event.currentTarget.contains(related)) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX >= bounds.left && event.clientX < bounds.right && event.clientY >= bounds.top && event.clientY < bounds.bottom) return;
        hovered.current = null; setTargetKey(null); setFeedback("");
      },
      onDrop(event: DragEvent<HTMLElement>) {
        const files = hasFiles(event.dataTransfer);
        if (!files && !captured.current) return;
        event.preventDefault(); event.stopPropagation();
        const batch = captured.current;
        const allowed = valid(target, files);
        stop(false);
        if (files) {
          if (allowed) upload(Array.from(event.dataTransfer.files), target);
          else { reject(blocked ? "Finish the current edit or save first." : "CSV uploads are unavailable here."); onFinish.current(); }
        } else if (batch) {
          if (allowed) move(batch, target);
          else { reject(blocked ? "Finish the current edit or save first." : target.archive ? "Active runs must finish before archiving." : "Choose a folder or Unfiled to move items."); onFinish.current(); }
        }
      },
    };
  }
  return { start, stop, bindings, dragging, paused, feedback };
}
