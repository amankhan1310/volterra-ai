import type { Simulation } from "../../api/types";
import { areaFill, baseOption } from "../../components/charts/baseOption";
import type { ChartTheme } from "../../components/charts/chartTheme";
import { finite, fixed } from "../../lib/format";

/** The prototype's limit on saved scenarios (decision D3). */
export const MAX_SCENARIOS = 4;
/** The prototype's limit on scenario names (decision U2; the API allows 60). */
export const NAME_MAX = 30;

/** Saved-scenario colours in order (legacy SCol / SC2), as theme keys. */
export const SCENARIO_TONES = ["am", "rd", "gr", "violet"] as const;
export type ScenarioTone = (typeof SCENARIO_TONES)[number];
export const scenarioTone = (index: number): ScenarioTone =>
  SCENARIO_TONES[index % SCENARIO_TONES.length] ?? "am";
/** The same colour as a CSS variable, for the HTML list (canvas charts use the theme). */
export const scenarioColor = (index: number) => `var(--${scenarioTone(index)})`;

/** Chart points: trajectories clamped at 0 and rounded to 2 decimals, as the prototype drew them. */
export function clampedSeries(
  cycles: readonly number[],
  values: readonly number[],
): [number, number][] {
  return cycles.map((c, i) => [
    c,
    Number(Math.max(0, values[i] ?? NaN).toFixed(2)),
  ]);
}

/** Lowest y: `floor(max(0, min(SOH after N, baseline SOH after N, EOL) − 3))`. */
export function simulatorFloor(sim: Simulation): number {
  const fin = finite(sim.soh_after_horizon.value) ?? 0;
  const finB = finite(sim.baseline_soh_after_horizon.value) ?? 0;
  return Math.floor(Math.max(0, Math.min(fin, finB, sim.params.eol_pct) - 3));
}

export interface Overlay {
  /** Stable series id (the saved scenario's id), so updates animate in place. */
  id: string;
  name: string;
  tone: ScenarioTone;
  sim: Simulation;
}

/** Baseline (dashed grey), Current (cyan with area, EOL line, end bubble) and saved overlays. */
export function simulatorOption(
  theme: ChartTheme,
  sim: Simulation,
  overlays: readonly Overlay[],
) {
  const n = sim.params.horizon_cycles;
  const eol = sim.params.eol_pct;
  const t = sim.trajectories;
  const cycles = t?.cycles ?? [];
  const fin = finite(sim.soh_after_horizon.value) ?? 0;
  return {
    ...baseOption(theme, {
      xMax: n,
      yMin: simulatorFloor(sim),
      yMax: 100,
      zoom: false,
      yFormat: "{value}%",
    }),
    series: [
      {
        id: "baseline",
        name: "Baseline",
        type: "line",
        showSymbol: false,
        data: clampedSeries(cycles, t?.baseline ?? []),
        lineStyle: { width: 1.6, type: "dashed", color: theme.mu },
        itemStyle: { color: theme.mu },
      },
      {
        id: "current",
        name: "Current",
        type: "line",
        showSymbol: false,
        data: clampedSeries(cycles, t?.scenario ?? []),
        lineStyle: { width: 2.6, color: theme.cy },
        itemStyle: { color: theme.cy },
        areaStyle: { color: areaFill(theme.cy) },
        markLine: {
          symbol: "none",
          silent: true,
          data: [
            {
              yAxis: eol,
              label: {
                formatter: `EOL ${String(eol)}%`,
                color: theme.rd,
                position: "insideEndTop",
              },
              lineStyle: { color: theme.rd, type: "dashed" },
            },
          ],
        },
        markPoint: {
          // The prototype marks the unclamped SOH after N cycles.
          data: [{ coord: [n, Number(fin.toFixed(2))], value: fixed(fin, 1) }],
          symbolSize: 44,
          itemStyle: { color: theme.cy },
          label: { color: theme.onAccent, fontSize: 10, fontWeight: 700 },
        },
      },
      ...overlays.map((o) => ({
        id: `scenario-${o.id}`,
        name: o.name,
        type: "line",
        showSymbol: false,
        data: clampedSeries(
          o.sim.trajectories?.cycles ?? [],
          o.sim.trajectories?.scenario ?? [],
        ),
        lineStyle: { width: 1.6, color: theme[o.tone] },
        itemStyle: { color: theme[o.tone] },
      })),
    ],
  };
}

/** Cycles to EOL as the prototype shows them: the number, or ">5000" when not reached. */
export const cyclesText = (cycles: number | null) =>
  cycles === null ? ">5000" : String(cycles);

/**
 * "+N cycles vs baseline (+P%)", coloured by sign; "–" when either side never reaches EOL.
 * When both sides are already at EOL the API sends delta_pct "NaN"; the prototype printed
 * "(NaN%)", this shows "(n/a)".
 */
export function deltaLine(sim: Simulation): {
  text: string;
  tone: "up" | "down" | "flat";
} {
  const dl = sim.delta_cycles;
  if (
    dl === null ||
    sim.cycles_to_eol === null ||
    sim.baseline_cycles_to_eol === null
  )
    return { text: "–", tone: "flat" };
  const pct = finite(sim.delta_pct);
  const pctText =
    pct === null ? "n/a" : `${pct > 0 ? "+" : ""}${pct.toFixed(0)}%`;
  return {
    text: `${dl > 0 ? "+" : ""}${String(dl)} cycles vs baseline (${pctText})`,
    tone: dl > 0 ? "up" : dl < 0 ? "down" : "flat",
  };
}

/** The value next to a slider label: "25 °C", "1 C", "600" (prototype `P[k] + " " + u`). */
export const sliderValueText = (value: number, unit: string) =>
  `${String(value)}${unit ? ` ${unit}` : ""}`;
