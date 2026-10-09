import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Expandable, ExpandableContent, ExpandableTrigger } from "./cult/Expandable";
import styles from "../views/data-protocol.module.css";

export function ProtocolDisclosure({ title, expanded, onToggle, children }: { title: string; expanded: boolean; onToggle: () => void; children: ReactNode }) {
  return <Expandable expanded={expanded} onToggle={onToggle} className={styles.disclosure}>
    <ExpandableTrigger><span>{title}</span><ChevronDown size={14} aria-hidden="true" /></ExpandableTrigger>
    <ExpandableContent className={styles.disclosureContent}>{children}</ExpandableContent>
  </Expandable>;
}
