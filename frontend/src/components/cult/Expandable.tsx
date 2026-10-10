import { useMotionPreference } from "../../hooks/useMotionPreference";
// Adapted from Cult UI's Expandable, ExpandableTrigger and ExpandableContent.
// https://cult-ui.com/r/expandable.json. MIT license: see LICENSE.
// Uses native buttons and immediate collapse so hidden rows cannot retain focus.
import { createContext, useContext, useId, type ComponentPropsWithoutRef, type ReactNode } from "react";
import { motion } from "motion/react";
import { motionTokens } from "@/registry/motion-tokens";

type Expansion = { expanded: boolean; toggle: () => void; contentId: string };
const ExpandableContext = createContext<Expansion | null>(null);

function useExpandable() {
  const context = useContext(ExpandableContext);
  if (!context) throw new Error("Expandable parts need an Expandable parent.");
  return context;
}

export function Expandable({ expanded, onToggle, children, ...props }: ComponentPropsWithoutRef<"div"> & {
  expanded: boolean; onToggle: () => void; children: ReactNode;
}) {
  const contentId = useId();
  return <ExpandableContext.Provider value={{ expanded, toggle: onToggle, contentId }}>
    <div {...props} data-expanded={expanded || undefined}>{children}</div>
  </ExpandableContext.Provider>;
}

export function ExpandableTrigger(props: ComponentPropsWithoutRef<"button">) {
  const { expanded, toggle, contentId } = useExpandable();
  return <button {...props} data-slot="expandable-trigger" type="button" aria-expanded={expanded} aria-controls={contentId} onClick={toggle} />;
}

export function ExpandableContent({ children, className }: { children: ReactNode; className?: string }) {
  const { expanded, contentId } = useExpandable();
  const reduced = useMotionPreference();
  return <div id={contentId} hidden={!expanded} className={className}>
    {expanded && <motion.div initial={{ opacity: reduced ? 1 : 0 }} animate={{ opacity: 1 }}
      transition={{ duration: reduced ? 0 : motionTokens.duration.fast, ease: motionTokens.ease.enter }}>{children}</motion.div>}
  </div>;
}
