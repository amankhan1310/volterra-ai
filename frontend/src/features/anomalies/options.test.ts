import { describe, expect, it } from "vitest";
import type { AnomalyEvent } from "../../api/types";
import { fixtures } from "../../test/msw";
import { theme } from "../../test/theme";
import { eventLabel } from "./AnomalyTimeline";
import {
  CHANNEL_CHARTS,
  LANES,
  TIMELINE,
  channelOption,
  eventValue,
  expectedRange,
  laneY,
  severityRule,
  timelineX,
} from "./options";

const events = fixtures.anomalies.events;
const event = (cycle: number): AnomalyEvent => {
  const e = events.find((x) => x.cycle === cycle);
  if (!e) throw new Error(`No event at cycle ${String(cycle)}`);
  return e;
};

interface Option {
  xAxis: { max: number };
  series: {
    id: string;
    type: string;
    data: [number, number][];
    lineStyle?: { color: string };
  }[];
}

describe("anomaly timeline geometry", () => {
  it("keeps the prototype's lanes, order and spacing", () => {
    expect(LANES.map((l) => l.channel)).toEqual(["temp", "volt", "soh"]);
    expect([0, 1, 2].map(laneY)).toEqual([24, 54, 84]);
  });

  it("maps cycle 0 and the last cycle to the ends of the track", () => {
    expect(timelineX(0, 319)).toBe(TIMELINE.left);
    expect(timelineX(319, 319)).toBe(TIMELINE.width - TIMELINE.right);
    expect(timelineX(160, 320)).toBeCloseTo(
      TIMELINE.left + (TIMELINE.width - TIMELINE.left - TIMELINE.right) / 2,
    );
  });

  it("does not divide by zero on a one-cycle dataset", () => {
    expect(timelineX(0, 0)).toBe(TIMELINE.left);
  });
});

describe("event formatting (prototype rules)", () => {
  it("shows voltage to 3 decimals and other channels to 2, with the unit", () => {
    expect(eventValue(event(130))).toBe("3.516 V");
    expect(eventValue(event(170))).toBe("36.40 °C");
    expect(eventValue(event(125))).toBe("-0.33 % resid.");
  });

  it("shows the expected range to 2 decimals", () => {
    expect(expectedRange(event(130))).toBe("3.60 to 3.78");
    expect(expectedRange(event(170))).toBe("14.38 to 34.86");
  });

  it("states the severity rule from the detector settings", () => {
    expect(severityRule(fixtures.anomalies.method)).toBe(
      "High = |z| above 6, medium = 3.5 to 6.",
    );
  });

  it("describes an event for its tooltip and screen readers", () => {
    expect(eventLabel(event(130))).toBe(
      "Cycle 130: Voltage dip/spike, high severity",
    );
    expect(eventLabel(event(170))).toBe(
      "Cycle 170: Temperature excursion, medium severity",
    );
  });
});

describe("channel charts", () => {
  it("plots every cycle and the channel's flagged events only", () => {
    const cycles = fixtures.cycles.items;
    for (const chart of CHANNEL_CHARTS) {
      const option = channelOption(
        theme,
        chart,
        cycles,
        events,
      ) as unknown as Option;
      const [line, flagged] = option.series;
      expect(option.xAxis.max).toBe(319);
      expect(line?.data).toHaveLength(cycles.length);
      expect(line?.data[0]).toEqual([0, cycles[0]?.[chart.field]]);
      expect(line?.lineStyle?.color).toBe(theme[chart.color]);
      expect(flagged?.type).toBe("scatter");
      expect(flagged?.data).toEqual(
        events
          .filter((e) => e.channel === chart.channel)
          .map((e) => [e.cycle, e.value]),
      );
    }
  });

  it("flags temperature at cycle 170 and voltage at 130 and 271, as the prototype", () => {
    const [temp, volt] = CHANNEL_CHARTS.map(
      (chart) =>
        channelOption(
          theme,
          chart,
          fixtures.cycles.items,
          events,
        ) as unknown as Option,
    );
    expect(temp?.series[1]?.data.map(([c]) => c)).toEqual([170]);
    expect(volt?.series[1]?.data.map(([c]) => c)).toEqual([130, 271]);
  });

  it("passes resolved colours, never CSS variables, to the canvas", () => {
    for (const chart of CHANNEL_CHARTS)
      expect(
        JSON.stringify(
          channelOption(theme, chart, fixtures.cycles.items, events),
        ),
      ).not.toContain("var(--");
  });
});
