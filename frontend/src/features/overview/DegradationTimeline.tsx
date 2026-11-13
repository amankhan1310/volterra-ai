import { useMemo, useState } from "react";
import type { Forecast } from "../../api/types";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { Segmented } from "../../components/ui/Segmented";
import { fixed } from "../../lib/format";
import { RECENT_WINDOW, timelineOption, type TimelineRange } from "./options";
import styles from "./Overview.module.css";

const RANGES = [
  { value: "all", label: "Full" },
  { value: "recent", label: `Last ${String(RECENT_WINDOW)}` },
] as const;

/** Rows of the screen-reader table: cycle, observed SOH and forecast SOH. */
export function timelineRows(forecast: Forecast): string[][] {
  const rows = new Map<number, [string, string]>();
  forecast.observed.cycles.forEach((c, i) => {
    rows.set(c, [fixed(forecast.observed.values[i], 2), "–"]);
  });
  forecast.forecast.cycles.forEach((c, i) => {
    const row = rows.get(c) ?? ["–", "–"];
    rows.set(c, [row[0], fixed(forecast.forecast.values[i], 2)]);
  });
  return [...rows.entries()].map(([c, [o, f]]) => [String(c), o, f]);
}

export function DegradationTimeline({
  forecast,
  eolPct,
  sohNow,
}: {
  forecast: Forecast;
  eolPct: number;
  sohNow: number;
}) {
  const theme = useChartTheme();
  const [range, setRange] = useState<TimelineRange>("all");
  const word =
    forecast.observed.provenance === "measured" ? "measured" : "simulated";
  const observedName = `Observed (${word})`;
  const option = useMemo(
    () =>
      timelineOption(theme, { forecast, eolPct, sohNow, range, observedName }),
    [theme, forecast, eolPct, sohNow, range, observedName],
  );
  return (
    <>
      <div className={styles.toolbar}>
        <div>
          <div className="lb">Degradation timeline</div>
          <p className={`mu ${styles.toolbarNote}`}>
            {observedName} vs. linear forecast
          </p>
        </div>
        <Segmented
          label="Timeline range"
          options={RANGES}
          value={range}
          onChange={setRange}
        />
      </div>
      <EChart
        option={option}
        label={`SOH over ${String(forecast.observed.cycles.length)} observed cycles with a linear forecast to cycle ${String(forecast.extent_cycles - 1)} and the ${String(eolPct)}% end-of-life threshold.`}
      />
      <ChartDataTable
        caption="Degradation timeline data (SOH, %)"
        columns={["Cycle", observedName, "Forecast (linear fit)"]}
        rows={timelineRows(forecast)}
      />
    </>
  );
}
