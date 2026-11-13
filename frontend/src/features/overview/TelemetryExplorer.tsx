import { useMemo, useState } from "react";
import type { Anomalies, Cycles } from "../../api/types";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { Segmented } from "../../components/ui/Segmented";
import {
  CHANNELS,
  CHANNEL_ORDER,
  flaggedPoints,
  telemetryOption,
  type TelemetryChannel,
} from "./options";
import styles from "./Overview.module.css";

const OPTIONS = CHANNEL_ORDER.map((value) => ({
  value,
  label: CHANNELS[value].label,
}));

export function TelemetryExplorer({
  cycles,
  anomalies,
}: {
  cycles: Cycles;
  anomalies: Anomalies;
}) {
  const theme = useChartTheme();
  // The prototype opens on Temperature.
  const [channel, setChannel] = useState<TelemetryChannel>("temp");
  const meta = CHANNELS[channel];
  const option = useMemo(
    () =>
      telemetryOption(theme, {
        channel,
        items: cycles.items,
        events: anomalies.events,
      }),
    [theme, channel, cycles, anomalies],
  );
  const flagged = new Set(
    flaggedPoints(channel, cycles.items, anomalies.events).map(([c]) => c),
  );
  return (
    <>
      <div className={styles.toolbar}>
        <div className="lb">Telemetry explorer</div>
        <Segmented
          label="Telemetry channel"
          options={OPTIONS}
          value={channel}
          onChange={setChannel}
        />
      </div>
      <EChart
        option={option}
        height={280}
        label={`${meta.label} per cycle, ${String(flagged.size)} flagged points.`}
      />
      <ChartDataTable
        caption={`${meta.label} per cycle (${meta.unit})`}
        columns={["Cycle", `${meta.label} (${meta.unit})`, "Flagged"]}
        rows={cycles.items.map((c) => [
          String(c.cycle),
          c[meta.field].toFixed(meta.dp),
          flagged.has(c.cycle) ? "Yes" : "",
        ])}
      />
    </>
  );
}
