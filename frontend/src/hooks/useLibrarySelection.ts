import { useEffect, useRef, useState } from "react";
import type { LibraryItem, LibraryItemRef } from "../api/types";

export const libraryItemKey = (item: LibraryItemRef) => `${item.kind}:${item.id}`;
export const libraryItemHref = (item: LibraryItem) => item.kind === "upload" ? `/new?source=upload&dataset=${item.id}`
  : `/experiments/${item.id}${item.status === "completed" ? "/comparison" : ""}`;

export function useLibrarySelection(visible: LibraryItem[], scope: string, announce: (message: string) => void) {
  const [selected, setSelected] = useState<string[]>([]);
  const [focused, setFocused] = useState<string | null>(null);
  const anchor = useRef<string | null>(null);
  const visibleKeys = visible.map(libraryItemKey).join(",");
  useEffect(() => {
    const keys = new Set(visibleKeys.split(","));
    setSelected(current => current.filter(value => keys.has(value)));
    setFocused(current => current && keys.has(current) ? current : null);
  }, [visibleKeys]);
  useEffect(() => { setSelected([]); setFocused(null); anchor.current = null; }, [scope]);
  const selection = visible.filter(item => selected.includes(libraryItemKey(item)));
  function limit(keys: string[]) {
    if (keys.length > 100) announce("Select up to 100 items at a time. The first 100 are selected.");
    return keys.slice(0, 100);
  }
  function select(item: LibraryItem, modifiers: { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean } = {}) {
    const id = libraryItemKey(item);
    setFocused(id);
    if (modifiers.shiftKey && anchor.current) {
      const start = visible.findIndex(value => libraryItemKey(value) === anchor.current);
      const end = visible.findIndex(value => libraryItemKey(value) === id);
      if (start >= 0 && end >= 0) {
        const range = visible.slice(Math.min(start, end), Math.max(start, end) + 1).map(libraryItemKey);
        setSelected(current => limit(modifiers.ctrlKey || modifiers.metaKey ? [...new Set([...current, ...range])] : range));
        return;
      }
    }
    anchor.current = id;
    if (modifiers.ctrlKey || modifiers.metaKey) setSelected(current => current.includes(id) ? current.filter(value => value !== id) : limit([...current, id]));
    else setSelected([id]);
  }
  function toggle(item: LibraryItem, checked: boolean) {
    anchor.current = libraryItemKey(item);
    setFocused(anchor.current);
    setSelected(current => checked ? limit([...new Set([...current, libraryItemKey(item)])]) : current.filter(value => value !== libraryItemKey(item)));
  }
  function selectAll(checked = true) { setSelected(checked ? limit(visible.map(libraryItemKey)) : []); }
  function clear() { setSelected([]); anchor.current = null; }
  return { selected, selection, focused, setFocused, select, toggle, selectAll, clear, setSelected };
}
