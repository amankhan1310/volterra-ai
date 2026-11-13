import type { ChartTheme } from "./chartTheme";
import { escapeHtml, withAlpha } from "./chartTheme";

/** The prototype's `eb(xm, y0, y1, zoom, fmt, dp)` arguments. */
export interface BaseOptionArgs {
  /** Last cycle on the x-axis. */
  xMax: number;
  /** Fixed y-axis bounds; `null` lets ECharts scale to the data. */
  yMin: number | null;
  yMax: number | null;
  /** Adds scroll/drag zoom and the slider below the plot. */
  zoom: boolean;
  /** Axis label template, e.g. "{value}%". */
  yFormat?: string;
  /** Decimals in the tooltip. */
  dp?: number;
}

interface TooltipParam {
  marker?: unknown;
  seriesName?: unknown;
  value?: unknown;
}

/** Tooltip text: "Cycle N" then one line per series, values to `dp` decimals (prototype format). */
export function tooltipFormatter(dp: number) {
  return (input: unknown): string => {
    const params = (Array.isArray(input) ? input : [input]) as TooltipParam[];
    const first = params[0]?.value;
    const cycle = Array.isArray(first) ? Number(first[0]) : NaN;
    const lines = params.map((p) => {
      const y = Array.isArray(p.value) ? Number(p.value[1]) : NaN;
      const marker = typeof p.marker === "string" ? p.marker : "";
      const name = typeof p.seriesName === "string" ? p.seriesName : "";
      return `<br>${marker}${escapeHtml(name)}: <b>${y.toFixed(dp)}</b>`;
    });
    return `Cycle ${String(Math.round(cycle))}${lines.join("")}`;
  };
}

/** Vertical gradient under a line: the colour at 22% opacity fading to transparent. */
export function areaFill(color: string) {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: withAlpha(color, 0.22) },
      { offset: 1, color: withAlpha(color, 0) },
    ],
  };
}

/** Port of the prototype's shared chart base (`eb` in legacy/ui.js), coloured from the theme. */
export function baseOption(theme: ChartTheme, args: BaseOptionArgs) {
  const { xMax, yMin, yMax, zoom, yFormat = "{value}", dp = 2 } = args;
  return {
    animationDuration: 700,
    textStyle: { fontFamily: theme.font },
    grid: { left: 52, right: 20, top: 36, bottom: zoom ? 64 : 30 },
    tooltip: {
      trigger: "axis",
      backgroundColor: theme.el,
      borderColor: theme.bd,
      textStyle: { color: theme.tx, fontSize: 12 },
      axisPointer: { lineStyle: { color: theme.bdStrong } },
      formatter: tooltipFormatter(dp),
    },
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: theme.mu },
      itemWidth: 14,
      itemHeight: 3,
      icon: "roundRect",
    },
    xAxis: {
      type: "value",
      min: 0,
      max: xMax,
      axisLabel: { color: theme.mu },
      axisLine: { lineStyle: { color: theme.bd } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: yMin,
      max: yMax,
      scale: yMin === null,
      axisLabel: { color: theme.mu, formatter: yFormat },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    dataZoom: zoom
      ? [
          { type: "inside", filterMode: "none" },
          {
            type: "slider",
            height: 16,
            bottom: 6,
            borderColor: theme.bd,
            fillerColor: theme.zoomFill,
            textStyle: { color: theme.mu },
          },
        ]
      : [],
  };
}
