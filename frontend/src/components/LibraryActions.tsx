import { useRef, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { MoreHorizontal } from "lucide-react";
import styles from "./experiment-library.module.css";

export function LibraryActions({ label, disabled, children, finalFocus }: {
  label: string; disabled?: boolean; children: (trigger: () => HTMLButtonElement | null) => ReactNode;
  finalFocus?: () => HTMLElement | null;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  return <Menu.Root><Menu.Trigger ref={trigger} className={styles.iconButton} aria-label={label} disabled={disabled}><MoreHorizontal size={18} aria-hidden="true" /></Menu.Trigger>
    <Menu.Portal><Menu.Positioner side="bottom" align="end" sideOffset={6} className={styles.layer}>
      <Menu.Popup className={styles.menu} finalFocus={() => finalFocus?.() ?? trigger.current}>{children(() => trigger.current)}</Menu.Popup>
    </Menu.Positioner></Menu.Portal>
  </Menu.Root>;
}
