// Menu surface adapted from Cult UI's Halo Select popup (MIT; see ../cult/LICENSE).
import { Menu } from "@base-ui/react/menu";
import { ChevronDown, Download } from "lucide-react";
import { Button } from "../Chrome";
import styles from "./export-menu.module.css";

export function ExportMenu({ busy, onExport }: { busy: boolean; onExport: (kind: "export" | "public") => void }) {
  return <Menu.Root modal={false}>
    <Menu.Trigger render={<Button variant="secondary" loading={busy} />} className={styles.trigger}><Download size={16} aria-hidden="true" />Export<ChevronDown className={styles.chevron} size={15} aria-hidden="true" /></Menu.Trigger>
    <Menu.Portal><Menu.Positioner side="bottom" align="end" sideOffset={8} className={styles.layer}>
      <Menu.Popup className={styles.popup}>
        <Menu.Item className={styles.item} onClick={() => onExport("export")}><strong>Full evidence</strong><span>Includes your concern</span></Menu.Item>
        <Menu.Item className={styles.item} onClick={() => onExport("public")}><strong>Public evidence</strong><span>Leaves out the concern, equipment IDs and raw readings</span></Menu.Item>
      </Menu.Popup>
    </Menu.Positioner></Menu.Portal>
  </Menu.Root>;
}
