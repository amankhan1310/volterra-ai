import { describe, expect, it } from "vitest";
import {
  areaFill,
  baseOption,
  tooltipFormatter,
} from "../../components/charts/baseOption";
import {
  escapeHtml,
  readChartTheme,
  withAlpha,
} from "../../components/charts/chartTheme";
import { sparklinePath } from "../../components/charts/Sparkline";
import { fixtures } from "../../test/msw";
import { theme } from "../../test/theme";
import {
  CHANNELS,
  flaggedPoints,
  telemetryOption,
  timelineFloor,
  timelineOption,
} from "./options";
import { INNER_C, OUTER_C, arcOffsets, gaugeTicks } from "./SohGauge";

interface Series {
  name: string;
  type: string;
  data: [number, number][];
  markLine?: {
    data: { xAxis?: number; yAxis?: number; label: { formatter: string } }[];
  };
}
interface Option {
  series: Series[];
  xAxis: { max: number };
  yAxis: { min: number | null; max: number | null; scale: boolean };
  dataZoom: { startValue?: number; endValue?: number }[];
}

describe("chart theme", () => {
  it("reads every colour from the CSS tokens: graphic accents for series, the text accent for labelled markers", () => {
    const root = document.documentElement.style;
    root.setProperty("--cy-fill", " #123456 ");
    root.setProperty("--cy", "#654321");
    root.setProperty("--rd-fill", "#abcdef");
    root.setProperty("--chart-grid", "red");
    const read = readChartTheme();
    expect(read.cy).toBe("#123456");
    expect(read.cyStrong).toBe("#654321");
    expect(read.rd).toBe("#abcdef");
    expect(read.grid).toBe("red");
    for (const token of ["--cy-fill", "--cy", "--rd-fill", "--chart-grid"])
      root.removeProperty(token);
  });

  it("adds alpha to hex colours and leaves other syntaxes alone", () => {
    expect(withAlpha("#7cf2bc", 0.22)).toBe("rgba(124, 242, 188, 0.22)");
    expect(withAlpha("var(--gr)", 0.5)).toBe("var(--gr)");
  });

  it("escapes HTML in tooltip text", () => {
    expect(escapeHtml(`<img src=x onerror="a('b')">&`)).toBe(
      "&lt;img src=x onerror=&quot;a(&#39;b&#39;)&quot;&gt;&amp;",
    );
  });
});

describe("base option (legacy eb)", () => {
  it("formats the tooltip as the prototype did, escaping series names", () => {
    const format = tooltipFormatter(3);
    expect(
      format([
        { marker: "<m>", seriesName: "Voltage (V)", value: [12.4, 3.65749] },
        { marker: "", seriesName: "<b>x</b>", value: [12.4, 1] },
      ]),
    ).toBe(
      "Cycle 12<br><m>Voltage (V): <b>3.657</b><br>&lt;b&gt;x&lt;/b&gt;: <b>1.000</b>",
    );
    expect(format({ seriesName: 7, value: 2 })).toBe(
      "Cycle NaN<br>: <b>NaN</b>",
    );
  });

  it("adds zoom controls and a larger bottom margin only when asked", () => {
    const zoomed = baseOption(theme, {
      xMax: 10,
      yMin: 1,
      yMax: 2,
      zoom: true,
    });
    expect(zoomed.grid.bottom).toBe(64);
    expect(zoomed.dataZoom).toHaveLength(2);
    expect(zoomed.yAxis.scale).toBe(false);
    const plain = baseOption(theme, {
      xMax: 10,
      yMin: null,
      yMax: null,
      zoom: false,
    });
    expect(plain.grid.bottom).toBe(30);
    expect(plain.dataZoom).toEqual([]);
    expect(plain.yAxis.scale).toBe(true);
  });

  it("fades the area fill from 22% to transparent", () => {
    expect(areaFill(theme.gr).colorStops).toEqual([
      { offset: 0, color: "rgba(124, 242, 188, 0.22)" },
      { offset: 1, color: "rgba(124, 242, 188, 0)" },
    ]);
  });
});

describe("degradation timeline", () => {
  const build = (range: "all" | "recent", eolPct = 80) =>
    timelineOption(theme, {
      forecast: fixtures.forecast,
      eolPct,
      sohNow: 86.08941987140724,
      range,
      observedName: "Observed (simulated)",
    }) as unknown as Option;

  it("floors the y-axis at min(EOL, SOH) − 3", () => {
    expect(timelineFloor(80, 86.09)).toBe(77);
    expect(timelineFloor(90, 86.09)).toBe(83);
    expect(build("all").yAxis).toMatchObject({ min: 77, max: 100 });
  });

  it("plots the API series to two decimals, with the forecast start and EOL markers", () => {
    const option = build("all");
    expect(option.xAxis.max).toBe(477);
    const [observed, forecast] = option.series;
    expect(observed?.data).toHaveLength(320);
    expect(observed?.data[0]).toEqual([0, 99.9]);
    expect(forecast?.data).toHaveLength(159);
    expect(forecast?.data[0]).toEqual([319, 86.09]);
    expect(observed?.markLine?.data.map((m) => m.label.formatter)).toEqual([
      "Forecast starts",
      "EOL 80%",
    ]);
    expect(observed?.markLine?.data[0]?.xAxis).toBe(319);
    expect(observed?.markLine?.data[1]?.yAxis).toBe(80);
  });

  it("never passes CSS variables to the canvas", () => {
    expect(JSON.stringify(build("all"))).not.toContain("var(--");
    expect(
      JSON.stringify(
        telemetryOption(theme, {
          channel: "temp",
          items: fixtures.cycles.items,
          events: fixtures.anomalies.events,
        }),
      ),
    ).not.toContain("var(--");
  });

  it("zooms to the last 120 observed cycles or the full range", () => {
    for (const z of build("recent").dataZoom)
      expect(z).toMatchObject({ startValue: 200, endValue: 477 });
    for (const z of build("all").dataZoom)
      expect(z).toMatchObject({ startValue: 0, endValue: 477 });
  });
});

describe("telemetry explorer", () => {
  const { items } = fixtures.cycles;
  const { events } = fixtures.anomalies;

  it("marks temperature and voltage events at their measured values", () => {
    expect(flaggedPoints("temp", items, events)).toEqual([
      [170, 36.400061569997774],
    ]);
    expect(flaggedPoints("volt", items, events).map(([c]) => c)).toEqual([
      130, 271,
    ]);
  });

  it("marks capacity-step events on the SOH line, not at their residual", () => {
    const points = flaggedPoints("soh", items, events);
    expect(points.map(([c]) => c)).toEqual([125, 127, 254, 315, 319]);
    for (const [, y] of points) expect(y).toBeGreaterThan(80);
    expect(
      flaggedPoints("soh", items.slice(0, 126), events).map(([c]) => c),
    ).toEqual([125]);
  });

  it("has no detector on capacity, so nothing is flagged there", () => {
    expect(flaggedPoints("cap", items, events)).toEqual([]);
    const option = telemetryOption(theme, {
      channel: "cap",
      items,
      events,
    }) as unknown as Option;
    expect(option.series.map((s) => s.name)).toEqual(["Capacity (Ah)"]);
  });

  it("uses each channel's unit, colour and decimals", () => {
    const option = telemetryOption(theme, {
      channel: "volt",
      items,
      events,
    }) as unknown as Option & {
      yAxis: { axisLabel: { formatter: string } };
      tooltip: { formatter: (p: unknown) => string };
    };
    expect(option.series.map((s) => s.name)).toEqual([
      "Voltage (V)",
      "Flagged",
    ]);
    expect(option.yAxis.axisLabel.formatter).toBe("{value}");
    expect(option.xAxis.max).toBe(319);
    expect(option.tooltip.formatter([{ value: [1, 3.7] }])).toContain("3.700");
    const soh = telemetryOption(theme, {
      channel: "soh",
      items,
      events,
    }) as unknown as { yAxis: { axisLabel: { formatter: string } } };
    expect(soh.yAxis.axisLabel.formatter).toBe("{value}%");
    expect(CHANNELS.temp.dp).toBe(2);
    expect(
      telemetryOption(theme, { channel: "temp", items: [], events: [] }),
    ).toMatchObject({ xAxis: { max: 0 } });
  });
});

describe("gauge and sparkline geometry", () => {
  it("lights the ticks up to SOH × 0.6 and makes every fifth tick long", () => {
    const ticks = gaugeTicks(86.08941987140724);
    expect(ticks).toHaveLength(60);
    expect(ticks.filter((t) => t.lit)).toHaveLength(52); // k = 0..51
    expect(ticks.filter((t) => t.major)).toHaveLength(12);
    expect(ticks[0]).toEqual({
      x1: 170,
      y1: 37,
      x2: 170,
      y2: 26,
      major: true,
      lit: true,
    });
  });

  it("sizes the arcs from SOH and the life used, clamped to [0, 1]", () => {
    expect(arcOffsets(100, 0)).toEqual({ outer: 0, inner: INNER_C });
    expect(arcOffsets(50, 2).inner).toBe(0);
    expect(arcOffsets(50, -1).inner).toBe(INNER_C);
    expect(arcOffsets(50, 0.5).outer).toBeCloseTo(OUTER_C / 2);
  });

  it("samples every fourth value into a 120 × 40 path", () => {
    expect(sparklinePath([0, 9, 9, 9, 10, 9, 9, 9, 5])).toBe(
      "M0.0 37.0L60.0 3.0L120.0 20.0",
    );
    expect(sparklinePath([4, 4, 4, 4, 4])).toBe("M0.0 37.0L120.0 37.0");
    expect(sparklinePath([7])).toBe("M0.0 37.0");
    expect(sparklinePath([])).toBe("");
  });
});
