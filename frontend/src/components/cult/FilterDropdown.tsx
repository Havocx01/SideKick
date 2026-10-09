// Select layout and indicators adapted from Cult UI's Halo Select.
// https://cult-ui.com/r/halo-select.json. MIT license: see LICENSE.
import { useId } from "react";
import { Popover } from "@base-ui/react/popover";
import { Select } from "@base-ui/react/select";
import { Check, ChevronDown } from "lucide-react";
import { Button } from "../Chrome";
import styles from "./filter-dropdown.module.css";

type FilterGroup = {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onValueChange: (value: string) => void;
};

export function FilterDropdown({ groups, activeCount, disabled, onClear }: {
  groups: FilterGroup[]; activeCount: number; disabled: boolean; onClear: () => void;
}) {
  const fieldId = useId();
  return <Popover.Root modal={false}>
    <Popover.Trigger render={<Button variant="ghost" />} className={styles.trigger} disabled={disabled}>
      Filters{activeCount > 0 && <span className={styles.count} aria-label={`${activeCount} filters applied`}>{activeCount}</span>}<ChevronDown className={styles.chevron} size={15} aria-hidden="true" />
    </Popover.Trigger>
    <Popover.Portal><Popover.Positioner side="bottom" align="end" sideOffset={8} className={styles.layer}>
      <Popover.Popup className={styles.popup} aria-label="Library filters">
        <div className={styles.fields}>
          {groups.map((group, index) => <div className={styles.field} key={group.label}>
            <label id={`${fieldId}-${index}`}>{group.label}</label>
            <Select.Root modal={false} items={group.options} value={group.value} disabled={disabled}
              onValueChange={value => { if (value !== null) group.onValueChange(value); }}>
              <Select.Trigger className={styles.select} aria-labelledby={`${fieldId}-${index}`}>
                <Select.Value /><Select.Icon><ChevronDown size={14} aria-hidden="true" /></Select.Icon>
              </Select.Trigger>
              <Select.Portal><Select.Positioner sideOffset={4} alignItemWithTrigger={false} className={styles.selectLayer}>
                <Select.Popup className={styles.options}><Select.List>
                  {group.options.map(option => <Select.Item className={styles.item} key={option.value} value={option.value}>
                    <Select.ItemText>{option.label}</Select.ItemText>
                    <Select.ItemIndicator><Check size={14} aria-hidden="true" /></Select.ItemIndicator>
                  </Select.Item>)}
                </Select.List></Select.Popup>
              </Select.Positioner></Select.Portal>
            </Select.Root>
          </div>)}
        </div>
        {activeCount > 0 && <footer className={styles.footer}>
          <Button variant="ghost" disabled={disabled} onClick={onClear}>Reset filters</Button>
        </footer>}
      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}
