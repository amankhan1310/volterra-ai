import { useSearchParams } from "react-router";
import {
  BATTERY_PARAM,
  batteryKey,
  useBatteries,
  useDefaultBattery,
} from "../../api/hooks";
import type { Battery } from "../../api/types";

function groupByDataset(items: readonly Battery[]) {
  const groups = new Map<string, Battery[]>();
  for (const b of items) {
    const list = groups.get(b.dataset_name) ?? [];
    list.push(b);
    groups.set(b.dataset_name, list);
  }
  return [...groups.entries()];
}

/** Option text: battery, cycles, and whether the analytics can run (decisions D4, D11). */
export function batteryOptionLabel(b: Battery): string {
  const kind = b.is_synthetic ? "synthetic" : "measured";
  const analysis = b.analysis.available ? "" : " · data view only";
  return `${b.external_id} · ${String(b.cycle_count)} cycles · ${kind}${analysis}`;
}

/**
 * Chooses the battery every page shows. The choice lives in the URL (`?battery=`), so it survives
 * reloads, can be bookmarked and is kept while navigating.
 */
export function BatterySelect({
  className,
  label = "Battery",
}: {
  className?: string | undefined;
  /** Accessible name; unique per page. */
  label?: string;
}) {
  const batteries = useBatteries();
  const { battery } = useDefaultBattery();
  const [params, setParams] = useSearchParams();
  const items = batteries.data?.items;
  if (!items || items.length === 0) return null;
  return (
    <select
      className={className}
      aria-label={label}
      value={battery ? batteryKey(battery) : ""}
      onChange={(e) => {
        const next = new URLSearchParams(params);
        next.set(BATTERY_PARAM, e.target.value);
        setParams(next);
      }}
    >
      {battery ? null : (
        <option value="" disabled>
          Choose a battery…
        </option>
      )}
      {groupByDataset(items).map(([name, list]) => (
        <optgroup key={name} label={name}>
          {list.map((b) => (
            <option key={b.id} value={batteryKey(b)}>
              {batteryOptionLabel(b)}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
