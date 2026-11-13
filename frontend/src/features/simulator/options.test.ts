import { describe, expect, it } from "vitest";
import type { Simulation } from "../../api/types";
import { fixtures } from "../../test/msw";
import { theme } from "../../test/theme";
import {
  clampedSeries,
  cyclesText,
  deltaLine,
  scenarioColor,
  scenarioTone,
  simulatorFloor,
  simulatorOption,
  sliderValueText,
} from "./options";
import { scenarioSummary } from "./SavedScenarios";
import { modelNote } from "./SimulatorPage";

interface Series {
  name: string;
  data: [number, number][];
  markPoint?: { data: { coord: [number, number]; value: string }[] };
  markLine?: { data: { yAxis: number; label: { formatter: string } }[] };
}

const sim = fixtures.simulateDefault;
const hot = fixtures.simulateT35;

describe("simulator chart (legacy simDraw)", () => {
  it("clamps trajectories at 0 and rounds to 2 decimals", () => {
    expect(clampedSeries([0, 1, 2], [86.104, -3, 0.005])).toEqual([
      [0, 86.1],
      [1, 0],
      [2, 0.01],
    ]);
  });

  it("floors the y-axis at max(0, min(SOH after N, baseline, EOL) − 3)", () => {
    expect(simulatorFloor(sim)).toBe(37); // 40.73 − 3
    expect(simulatorFloor(hot)).toBe(0); // 3.42 − 3 → 0.42 → 0
  });

  it("draws baseline, current with the EOL line and end bubble, and overlays", () => {
    const option = simulatorOption(theme, hot, [
      { id: "a", name: "Scenario 1", tone: scenarioTone(0), sim },
    ]) as unknown as { series: Series[]; xAxis: { max: number } };
    expect(option.xAxis.max).toBe(600);
    expect(option.series.map((s) => s.name)).toEqual([
      "Baseline",
      "Current",
      "Scenario 1",
    ]);
    const current = option.series[1];
    expect(current?.data).toHaveLength(601);
    expect(current?.markLine?.data[0]?.label.formatter).toBe("EOL 80%");
    expect(current?.markPoint?.data[0]).toEqual({
      coord: [600, 3.42],
      value: "3.4",
    });
    expect(option.series[2]?.data[600]).toEqual([600, 40.73]);
    // Canvas cannot resolve CSS variables: overlays use the resolved theme colour.
    expect(
      (option.series[2] as unknown as { lineStyle: { color: string } })
        .lineStyle.color,
    ).toBe(theme.am);
    expect(JSON.stringify(option)).not.toContain("var(--");
  });
});

describe("result text", () => {
  it("shows >5000 when EOL is never reached", () => {
    expect(cyclesText(null)).toBe(">5000");
    expect(cyclesText(106)).toBe("106");
  });

  it("signs and colours the change versus baseline", () => {
    expect(deltaLine(hot)).toEqual({
      text: "-46 cycles vs baseline (-43%)",
      tone: "down",
    });
    expect(deltaLine(sim)).toEqual({
      text: "0 cycles vs baseline (0%)",
      tone: "flat",
    });
    const better: Simulation = {
      ...sim,
      cycles_to_eol: 150,
      delta_cycles: 44,
      delta_pct: 41.5,
    };
    expect(deltaLine(better)).toEqual({
      text: "+44 cycles vs baseline (+42%)",
      tone: "up",
    });
    expect(
      deltaLine({ ...sim, cycles_to_eol: null, delta_cycles: null }),
    ).toEqual({ text: "–", tone: "flat" });
    expect(
      deltaLine({
        ...sim,
        cycles_to_eol: 0,
        baseline_cycles_to_eol: 0,
        delta_cycles: 0,
        delta_pct: "NaN" as unknown as number,
      }).text,
    ).toBe("0 cycles vs baseline (n/a)");
  });

  it("formats slider values and saved-scenario summaries like the prototype", () => {
    expect(sliderValueText(25, "°C")).toBe("25 °C");
    expect(sliderValueText(600, "")).toBe("600");
    expect(sliderValueText(0.5, "C")).toBe("0.5 C");
    expect(scenarioSummary(fixtures.scenario)).toBe("25°C · 1C · 80%");
    expect(scenarioColor(3)).toBe("var(--violet)");
    expect(scenarioColor(4)).toBe("var(--am)");
  });

  it("builds the model note from the API's coefficients", () => {
    expect(modelNote(fixtures.simulator)).toBe(
      "Model: SOH(n) = SOH₀ − r·n·(1 + n/1500), r = recent fitted fade × e^(0.06·(T−25)) × (1 + 0.4·(C−1)) × (DoD/80)^0.9. The temperature, C-rate and DoD coefficients are assumed, not fitted. Outputs are simulated estimates.",
    );
    expect(modelNote({ ...fixtures.simulator, coefficients: [] })).toContain(
      "n/?",
    );
  });
});

describe("missing data", () => {
  it("draws empty series when the API sends no trajectories or non-finite SOH", () => {
    const bare: Simulation = {
      ...sim,
      trajectories: null,
      soh_after_horizon: { ...sim.soh_after_horizon, value: null },
      baseline_soh_after_horizon: {
        ...sim.baseline_soh_after_horizon,
        value: "NaN" as unknown as number,
      },
    };
    expect(simulatorFloor(bare)).toBe(0);
    const option = simulatorOption(theme, bare, [
      { id: "b", name: "Old", tone: scenarioTone(0), sim: bare },
    ]) as unknown as { series: Series[] };
    expect(option.series.map((s) => s.data)).toEqual([[], [], []]);
    expect(option.series[1]?.markPoint?.data[0]).toEqual({
      coord: [600, 0],
      value: "0.0",
    });
    expect(clampedSeries([0, 1], [5])).toEqual([
      [0, 5],
      [1, NaN],
    ]);
  });
});
