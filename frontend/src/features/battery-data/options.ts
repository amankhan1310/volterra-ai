import type { Cycle, CycleSamples } from "../../api/types";
import { baseOption } from "../../components/charts/baseOption";
import {
  escapeHtml,
  type ChartTheme,
} from "../../components/charts/chartTheme";

/** Per-cycle channels of the cycles endpoint that the Battery Data chart can show. */
export const CYCLE_CHANNELS = {
  capacity_ah: { label: "Capacity", unit: "Ah", dp: 3 },
  soh_pct: { label: "SOH", unit: "%", dp: 2 },
  temp_c: { label: "Temperature", unit: "°C", dp: 2 },
  voltage_v: { label: "Voltage", unit: "V", dp: 3 },
  internal_resistance_ohm: { label: "Resistance", unit: "Ω", dp: 4 },
  charge_time_s: { label: "Charge time", unit: "s", dp: 0 },
} as const;
export type CycleChannel = keyof typeof CYCLE_CHANNELS;

export const SAMPLE_CHANNELS = {
  voltage_v: { label: "Voltage", unit: "V", dp: 3 },
  current_a: { label: "Current", unit: "A", dp: 3 },
  temp_c: { label: "Temperature", unit: "°C", dp: 2 },
} as const;
export type SampleChannel = keyof typeof SAMPLE_CHANNELS;

/** Measured points of one channel; cycles without a measurement are left out, never filled. */
export function cyclePoints(
  cycles: readonly Cycle[],
  channel: CycleChannel,
): [number, number][] {
  return cycles.flatMap((c) => {
    const v = c[channel];
    return v === null ? [] : [[c.cycle, v] as [number, number]];
  });
}

/** Channels with at least one measured value (the others are listed as not measured). */
export function measuredCycleChannels(cycles: readonly Cycle[]): {
  measured: CycleChannel[];
  missing: CycleChannel[];
} {
  const keys = Object.keys(CYCLE_CHANNELS) as CycleChannel[];
  const measured = keys.filter((k) => cycles.some((c) => c[k] !== null));
  return { measured, missing: keys.filter((k) => !measured.includes(k)) };
}

export function samplePoints(
  samples: CycleSamples,
  channel: SampleChannel,
): [number, number][] {
  return samples.items.flatMap((s) => {
    const v = s[channel];
    return v === null || s.time_s === null
      ? []
      : [[s.time_s, v] as [number, number]];
  });
}

export function cycleChartOption(
  theme: ChartTheme,
  points: [number, number][],
  channel: CycleChannel,
  flagged: [number, number][],
  /** Ends of the API's fitted capacity line (capacity channel only); drawn, never computed. */
  trend: [number, number][] = [],
) {
  const meta = CYCLE_CHANNELS[channel];
  const last = points.at(-1)?.[0] ?? 0;
  const base = baseOption(theme, {
    xMax: last,
    yMin: null,
    yMax: null,
    zoom: points.length > 60,
    dp: meta.dp,
  });
  return {
    ...base,
    xAxis: {
      ...base.xAxis,
      name: "Cycle",
      nameLocation: "middle",
      nameGap: 26,
    },
    series: [
      {
        name: `${meta.label} (measured)`,
        type: "line",
        data: points,
        showSymbol: false,
        lineStyle: { width: 2, color: theme.cy },
        itemStyle: { color: theme.cy },
      },
      {
        name: "Flagged cycle",
        type: "scatter",
        data: flagged,
        symbolSize: 6,
        itemStyle: { color: theme.am },
      },
      ...(trend.length === 2
        ? [
            {
              name: "Fitted trend (recorded cycles)",
              type: "line",
              data: trend,
              showSymbol: false,
              lineStyle: { width: 2, type: "dashed", color: theme.violet },
              itemStyle: { color: theme.violet },
            },
          ]
        : []),
    ],
  };
}

export function sampleChartOption(
  theme: ChartTheme,
  points: [number, number][],
  channel: SampleChannel,
) {
  const meta = SAMPLE_CHANNELS[channel];
  // Whole seconds for the axis end, so its label is not a raw float such as 2461.1012.
  const last = Math.ceil(points.at(-1)?.[0] ?? 0);
  const base = baseOption(theme, {
    xMax: last,
    yMin: null,
    yMax: null,
    zoom: false,
    dp: meta.dp,
  });
  return {
    ...base,
    xAxis: {
      ...base.xAxis,
      min: points[0]?.[0] ?? 0,
      name: "Time (s)",
      nameLocation: "middle",
      nameGap: 26,
    },
    tooltip: {
      ...base.tooltip,
      formatter: (input: unknown) => {
        const p = (Array.isArray(input) ? input[0] : input) as {
          value?: unknown;
        };
        const pair: unknown[] = Array.isArray(p.value) ? p.value : [];
        const [t, v] = pair;
        return `t = ${escapeHtml(Number(t).toFixed(1))} s<br>${escapeHtml(meta.label)}: <b>${escapeHtml(Number(v).toFixed(meta.dp))} ${escapeHtml(meta.unit)}</b>`;
      },
    },
    series: [
      {
        name: `${meta.label} (measured)`,
        type: "line",
        data: points,
        showSymbol: false,
        lineStyle: { width: 2, color: theme.ib },
        itemStyle: { color: theme.ib },
      },
    ],
  };
}

export interface RulSeries {
  predicted: [number, number][];
  lower: [number, number][];
  upper: [number, number][];
  actual: [number, number][];
}

/** The stored predictions as chart series (values copied from the API; nothing recomputed). */
export function rulSeries(
  points: readonly {
    cycle: number;
    rul: { point: number | null; lower: number | null; upper: number | null };
    actual_rul: { value: number | null } | null;
  }[],
): RulSeries {
  const pick = (v: number | null | undefined, cycle: number) =>
    v === null || v === undefined ? [] : [[cycle, v] as [number, number]];
  return {
    predicted: points.flatMap((p) => pick(p.rul.point, p.cycle)),
    lower: points.flatMap((p) => pick(p.rul.lower, p.cycle)),
    upper: points.flatMap((p) => pick(p.rul.upper, p.cycle)),
    actual: points.flatMap((p) => pick(p.actual_rul?.value, p.cycle)),
  };
}

export function rulChartOption(theme: ChartTheme, s: RulSeries) {
  const last = s.predicted.at(-1)?.[0] ?? 0;
  const base = baseOption(theme, {
    xMax: last,
    yMin: 0,
    yMax: null,
    zoom: s.predicted.length > 60,
    dp: 0,
  });
  const bound = (name: string, data: [number, number][]) => ({
    name,
    type: "line",
    data,
    showSymbol: false,
    lineStyle: { width: 1, type: "dashed", color: theme.cy },
    itemStyle: { color: theme.cy },
  });
  return {
    ...base,
    xAxis: {
      ...base.xAxis,
      name: "Cycle",
      nameLocation: "middle",
      nameGap: 26,
    },
    yAxis: { ...base.yAxis, name: "Cycles to EOL" },
    series: [
      {
        name: "Predicted RUL",
        type: "line",
        data: s.predicted,
        showSymbol: false,
        lineStyle: { width: 2, color: theme.cy },
        itemStyle: { color: theme.cy },
      },
      bound("90% interval (lower)", s.lower),
      bound("90% interval (upper)", s.upper),
      {
        name: "Actual RUL",
        type: "line",
        data: s.actual,
        showSymbol: false,
        lineStyle: { width: 2, color: theme.gr },
        itemStyle: { color: theme.gr },
      },
    ],
  };
}
