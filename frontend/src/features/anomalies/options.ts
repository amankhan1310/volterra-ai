import type { Anomalies, AnomalyEvent, Cycle } from "../../api/types";
import { baseOption } from "../../components/charts/baseOption";
import type { ChartTheme } from "../../components/charts/chartTheme";

type Channel = AnomalyEvent["channel"];

/** Timeline lanes in the prototype's order (`L` in legacy ui.js `pages.anom`). */
export const LANES: readonly { channel: Channel; label: string }[] = [
  { channel: "temp", label: "Temperature" },
  { channel: "volt", label: "Voltage" },
  { channel: "soh", label: "Capacity" },
];

/**
 * Timeline drawing: 720 × 120 like the prototype, with room for full lane names. The component
 * redraws at its measured width (never below `minWidth`) so labels stay 11 px on a phone.
 */
export const TIMELINE = {
  width: 720,
  minWidth: 320,
  height: 120,
  left: 92,
  right: 10,
};

export function laneY(index: number): number {
  return 24 + index * 30;
}

/** x of a cycle on the timeline (the prototype's `X(c)`, with a wider label column). */
export function timelineX(
  cycle: number,
  lastCycle: number,
  width: number = TIMELINE.width,
): number {
  const span = width - TIMELINE.left - TIMELINE.right;
  return TIMELINE.left + (cycle / (lastCycle || 1)) * span;
}

export const SEVERITY_LABEL = { high: "High", medium: "Medium" } as const;
export const SEVERITY_COLOR = {
  high: "var(--rd)",
  medium: "var(--am)",
} as const;

/** Event value with its unit; voltage to 3 decimals, everything else to 2 (prototype rule). */
export function eventValue(e: AnomalyEvent): string {
  return `${e.value.toFixed(e.channel === "volt" ? 3 : 2)} ${e.unit}`;
}

export function expectedRange(e: AnomalyEvent): string {
  return `${e.expected_low.toFixed(2)} to ${e.expected_high.toFixed(2)}`;
}

/** "High = |z| above 6, medium = 3.5 to 6." from the detector settings the API reports. */
export function severityRule(method: Anomalies["method"]): string {
  const hi = String(method.high_severity_abs_z);
  const lo = String(method.flag_threshold_abs_z);
  return `High = |z| above ${hi}, medium = ${lo} to ${hi}.`;
}

export interface ChannelChart {
  channel: "temp" | "volt";
  label: string;
  unit: string;
  field: "temp_c" | "voltage_v";
  dp: number;
  color: keyof Pick<ChartTheme, "cy" | "gr">;
}

/** The two channel charts under the timeline (legacy ui.js `go` override for `anom`). */
export const CHANNEL_CHARTS: readonly ChannelChart[] = [
  {
    channel: "temp",
    label: "Temperature",
    unit: "°C",
    field: "temp_c",
    dp: 2,
    color: "cy",
  },
  {
    channel: "volt",
    label: "Voltage",
    unit: "V",
    field: "voltage_v",
    dp: 3,
    color: "gr",
  },
];

export function channelOption(
  theme: ChartTheme,
  chart: ChannelChart,
  items: readonly Cycle[],
  events: readonly AnomalyEvent[],
) {
  const color = theme[chart.color];
  return {
    ...baseOption(theme, {
      xMax: items.at(-1)?.cycle ?? 0,
      yMin: null,
      yMax: null,
      zoom: false,
      dp: chart.dp,
    }),
    series: [
      {
        id: "values",
        name: `${chart.label} (${chart.unit})`,
        type: "line",
        showSymbol: false,
        data: items.map((c) => [c.cycle, c[chart.field]]),
        lineStyle: { width: 1.6, color },
        itemStyle: { color },
      },
      {
        id: "flagged",
        name: "Flagged",
        type: "scatter",
        symbolSize: 9,
        itemStyle: { color: theme.rd },
        data: events
          .filter((e) => e.channel === chart.channel)
          .map((e) => [e.cycle, e.value]),
      },
    ],
  };
}
