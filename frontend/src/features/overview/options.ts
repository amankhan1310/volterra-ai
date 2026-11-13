import type { AnomalyEvent, Cycle, Forecast } from "../../api/types";
import { areaFill, baseOption } from "../../components/charts/baseOption";
import type { ChartTheme } from "../../components/charts/chartTheme";
import { round2 } from "../../lib/format";

/** The prototype's "Last 120" range button. */
export const RECENT_WINDOW = 120;

export type TimelineRange = "all" | "recent";

/** Lowest y on the degradation timeline: `floor(min(EOL, SOH) − 3)`, as in the prototype. */
export function timelineFloor(eolPct: number, sohNow: number): number {
  return Math.floor(Math.min(eolPct, sohNow) - 3);
}

const pairs = (cycles: readonly number[], values: readonly number[]) =>
  cycles.map((c, i) => [c, round2(values[i] ?? NaN)] as [number, number]);

/** Degradation timeline: observed SOH, the linear forecast and the forecast-start/EOL markers. */
export function timelineOption(
  theme: ChartTheme,
  args: {
    forecast: Forecast;
    eolPct: number;
    sohNow: number;
    range: TimelineRange;
    observedName: string;
  },
) {
  const { forecast, eolPct, sohNow, range, observedName } = args;
  const xMax = forecast.extent_cycles - 1;
  const boundary = forecast.prediction_boundary_cycle;
  const base = baseOption(theme, {
    xMax,
    yMin: timelineFloor(eolPct, sohNow),
    yMax: 100,
    zoom: true,
    yFormat: "{value}%",
  });
  const startValue = range === "all" ? 0 : boundary + 1 - RECENT_WINDOW;
  return {
    ...base,
    dataZoom: base.dataZoom.map((z) => ({ ...z, startValue, endValue: xMax })),
    series: [
      {
        id: "observed",
        name: observedName,
        type: "line",
        showSymbol: false,
        data: pairs(forecast.observed.cycles, forecast.observed.values),
        lineStyle: { width: 2.2, color: theme.gr },
        itemStyle: { color: theme.gr },
        areaStyle: { color: areaFill(theme.gr) },
        markLine: {
          symbol: "none",
          silent: true,
          data: [
            {
              xAxis: boundary,
              label: { formatter: "Forecast starts", color: theme.mu },
              lineStyle: { color: theme.mu, type: "dotted" },
            },
            {
              yAxis: eolPct,
              label: {
                formatter: `EOL ${String(eolPct)}%`,
                color: theme.rd,
                position: "insideEndTop",
              },
              lineStyle: { color: theme.rd, type: "dashed" },
            },
          ],
        },
      },
      {
        id: "forecast",
        name: "Forecast (linear fit)",
        type: "line",
        showSymbol: false,
        data: pairs(forecast.forecast.cycles, forecast.forecast.values),
        lineStyle: { width: 2, type: "dashed", color: theme.cy },
        itemStyle: { color: theme.cy },
      },
    ],
  };
}

export type TelemetryChannel = "soh" | "temp" | "volt" | "cap";

interface ChannelMeta {
  label: string;
  unit: string;
  dp: number;
  color: keyof Pick<ChartTheme, "gr" | "cy" | "am" | "ib">;
  field: keyof Pick<Cycle, "soh_pct" | "temp_c" | "voltage_v" | "capacity_ah">;
}

/** Telemetry explorer channels, in the prototype's order, colours and decimals. */
export const CHANNELS: Record<TelemetryChannel, ChannelMeta> = {
  soh: { label: "SOH", unit: "%", dp: 2, color: "gr", field: "soh_pct" },
  temp: {
    label: "Temperature",
    unit: "°C",
    dp: 2,
    color: "cy",
    field: "temp_c",
  },
  volt: { label: "Voltage", unit: "V", dp: 3, color: "am", field: "voltage_v" },
  cap: {
    label: "Capacity",
    unit: "Ah",
    dp: 3,
    color: "ib",
    field: "capacity_ah",
  },
};

export const CHANNEL_ORDER: readonly TelemetryChannel[] = [
  "soh",
  "temp",
  "volt",
  "cap",
];

/**
 * Flagged points drawn on a channel. Temperature and voltage events carry the measured value.
 * Capacity-step events (`soh` channel) carry a residual, not an SOH, so they are drawn on the
 * SOH line at their cycle; the prototype plotted the residual itself (≈ ±0.3) on the SOH axis.
 * The capacity channel has no detector, as in the prototype.
 */
export function flaggedPoints(
  channel: TelemetryChannel,
  items: readonly Cycle[],
  events: readonly AnomalyEvent[],
): [number, number][] {
  if (channel === "cap") return [];
  const own = events.filter((e) => e.channel === channel);
  if (channel !== "soh") return own.map((e) => [e.cycle, e.value]);
  const byCycle = new Map(items.map((c) => [c.cycle, c.soh_pct]));
  return own.flatMap((e) => {
    const soh = byCycle.get(e.cycle);
    return soh === undefined ? [] : [[e.cycle, soh] as [number, number]];
  });
}

export function telemetryOption(
  theme: ChartTheme,
  args: {
    channel: TelemetryChannel;
    items: readonly Cycle[];
    events: readonly AnomalyEvent[];
  },
) {
  const { channel, items, events } = args;
  const meta = CHANNELS[channel];
  const color = theme[meta.color];
  const flagged = flaggedPoints(channel, items, events);
  const base = baseOption(theme, {
    xMax: items.at(-1)?.cycle ?? 0,
    yMin: null,
    yMax: null,
    zoom: false,
    yFormat: meta.unit === "%" ? "{value}%" : "{value}",
    dp: meta.dp,
  });
  const series: object[] = [
    {
      id: "telemetry",
      name: `${meta.label} (${meta.unit})`,
      type: "line",
      showSymbol: false,
      data: items.map((c) => [c.cycle, c[meta.field]]),
      lineStyle: { width: 1.8, color },
      itemStyle: { color },
    },
  ];
  if (flagged.length > 0)
    series.push({
      id: "flagged",
      name: "Flagged",
      type: "scatter",
      symbolSize: 9,
      itemStyle: { color: theme.rd },
      data: flagged,
    });
  return { ...base, series };
}
