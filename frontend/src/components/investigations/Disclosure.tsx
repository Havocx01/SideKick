import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Expandable, ExpandableContent, ExpandableTrigger } from "../cult/Expandable";
import styles from "../../views/investigations.module.css";

export function Disclosure({ title, children, initiallyOpen = false, description }: {
  title: string; children: ReactNode; initiallyOpen?: boolean; description?: string;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return <Expandable expanded={open} onToggle={() => setOpen(!open)} className={styles.disclosure}>
    <ExpandableTrigger className={styles.disclosureTrigger}><span>{title}{description && <small>{description}</small>}</span><ChevronDown size={16} aria-hidden="true" /></ExpandableTrigger>
    <ExpandableContent className={styles.disclosureContent}>{children}</ExpandableContent>
  </Expandable>;
}
