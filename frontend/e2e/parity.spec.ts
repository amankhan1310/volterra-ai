/**
 * Number parity with the frozen prototype (Phase 4 Definition of Done): every value the legacy
 * Overview and Digital Twin show must appear identically in React. The prototype computes in the
 * browser; React shows what the API returns, so this checks the whole chain (Python port → API →
 * UI).
 *
 * Needs the prototype served at LEGACY_URL (default http://127.0.0.1:8080/):
 *   python -m http.server 8080 --directory legacy
 */
import { expect, test, type Page } from "@playwright/test";
import { settled } from "./support";

const LEGACY_URL = process.env["LEGACY_URL"] ?? "http://127.0.0.1:8080/";

const clean = (s: string | null) => (s ?? "").replace(/\s+/g, " ").trim();

interface Values {
  soh: string;
  condition: string;
  explain: string;
  rul: string;
  stats: string[];
  kpiValues: string[];
  kpiNotes: string[];
  insights: string[];
  timeline: { observed: string[]; forecast: string[] };
  temperature: { values: string[]; flagged: number[] };
}

interface LegacyChart {
  getOption(): { series: { data: [number, number][] }[] };
}

async function legacyValues(page: Page): Promise<Values> {
  await page.goto(`${LEGACY_URL}#overview`);
  await page.locator("#tl canvas").first().waitFor();
  await page.locator("#tel canvas").first().waitFor();
  const texts = (selector: string) =>
    page.locator(selector).evaluateAll((els) => els.map((e) => e.textContent));
  const charts = await page.evaluate(() => {
    const ec = (
      window as unknown as {
        echarts: { getInstanceByDom(el: Element | null): LegacyChart };
      }
    ).echarts;
    const series = (id: string) =>
      ec.getInstanceByDom(document.getElementById(id)).getOption().series;
    return { tl: series("tl"), tel: series("tel") };
  });
  return {
    soh: clean(
      await page
        .locator('svg[aria-label^="State of health"]')
        .getAttribute("aria-label"),
    ),
    condition: clean(await page.locator(".cnd").textContent()),
    explain: clean(await page.locator(".hr > p.mu").first().textContent()),
    rul: clean(await page.locator(".hr .big.xl").textContent()),
    stats: (await texts(".stats b")).map(clean),
    kpiValues: (await texts(".k12 .card.hv .big")).map(clean),
    kpiNotes: (await texts(".k12 .card.hv > p.mu")).map(clean),
    insights: (await texts(".in p")).map(clean),
    timeline: {
      observed: (charts.tl[0]?.data ?? []).map(([, y]) => y.toFixed(2)),
      forecast: (charts.tl[1]?.data ?? []).map(([, y]) => y.toFixed(2)),
    },
    temperature: {
      values: (charts.tel[0]?.data ?? []).map(([, y]) => y.toFixed(2)),
      flagged: (charts.tel[1]?.data ?? []).map(([c]) => c),
    },
  };
}

async function reactValues(page: Page): Promise<Values> {
  await page.goto("/overview");
  await settled(page);
  const texts = async (testId: string) =>
    (await page.getByTestId(testId).allTextContents()).map(clean);
  const tableRows = (name: string) =>
    page
      .getByRole("table", { name, includeHidden: true })
      .locator("tbody tr")
      .evaluateAll((rows) =>
        rows.map((r) =>
          [...r.querySelectorAll("td")].map((td) => td.textContent),
        ),
      );
  const timeline = await tableRows("Degradation timeline data (SOH, %)");
  const temperature = await tableRows("Temperature per cycle (°C)");
  return {
    soh: clean(
      await page
        .locator('svg[aria-label^="State of health"]')
        .getAttribute("aria-label"),
    ),
    condition: clean(await page.getByTestId("condition").textContent()),
    explain: clean(await page.getByTestId("explain").textContent()),
    rul: clean(await page.getByTestId("rul").textContent()),
    stats: (
      await page.getByTestId("hero-stats").locator("b").allTextContents()
    ).map(clean),
    kpiValues: await texts("kpi-value"),
    kpiNotes: await texts("kpi-note"),
    insights: await texts("insight-text"),
    timeline: {
      observed: timeline.map((r) => r[1] ?? "").filter((v) => v !== "–"),
      forecast: timeline.map((r) => r[2] ?? "").filter((v) => v !== "–"),
    },
    temperature: {
      values: temperature.map((r) => r[1] ?? ""),
      flagged: temperature
        .filter((r) => r[2] === "Yes")
        .map((r) => Number(r[0])),
    },
  };
}

test("every Overview number matches the legacy prototype", async ({ page }) => {
  const legacy = await legacyValues(page);
  const react = await reactValues(page);
  // Guard against comparing two empty pages.
  expect(legacy.kpiValues).toHaveLength(6);
  expect(legacy.insights).toHaveLength(4);
  expect(legacy.timeline.observed.length).toBeGreaterThan(300);
  expect(react).toEqual(legacy);
});

interface TwinValues {
  heading: string;
  stats: string[];
  message: string;
  fill: string;
  legend: string[];
}

/** Digital Twin parity at the first, middle, warm-excursion and latest cycles, both modes. */
for (const [cycle, mode] of [
  [0, "soh"],
  [160, "soh"],
  [170, "temp"],
  [319, "soh"],
  [319, "temp"],
] as const) {
  test(`Digital Twin at cycle ${String(cycle)} (${mode}) matches the legacy prototype`, async ({
    page,
  }) => {
    await page.goto(`${LEGACY_URL}#digital`);
    await page.locator("#pack .mod").first().waitFor();
    await page.evaluate(
      ([c, m]) => {
        const slider = document.getElementById("cs") as HTMLInputElement;
        slider.value = String(c);
        slider.dispatchEvent(new Event("input"));
        if (m === "temp")
          (
            document.querySelector('#sg button[data-m="temp"]') as HTMLElement
          ).click();
      },
      [cycle, mode] as const,
    );
    const legacy: TwinValues = await page.evaluate(() => {
      const info = document.getElementById("tinfo") as HTMLElement;
      const text = (e: Element | null) =>
        (e?.textContent ?? "").replace(/\s+/g, " ").trim();
      return {
        heading: text(info.querySelector(".lb")),
        stats: [...info.querySelectorAll(".stats2 .big")].map(text),
        message: text(info.querySelector("p.mu")),
        fill: (document.querySelector("#pack .mod .t") as SVGElement).style
          .fill,
        // Prototype defect: the logo's SVG gradient also has id="lg", so the legend is written
        // into that gradient and never shown (and the logo icon disappears). Its text is still
        // the intended legend, which React displays.
        legend: [...document.querySelectorAll("#lg span")].map(text),
      };
    });

    await page.goto("/digital-twin");
    await settled(page);
    await page.getByRole("slider", { name: /Cycle/ }).fill(String(cycle));
    if (mode === "temp")
      await page
        .getByRole("group", { name: "Colour modules by" })
        .getByRole("button", { name: "Temperature" })
        .click();
    await expect(page.getByTestId("page-content")).toContainText(
      `Pack state at cycle ${String(cycle)}`,
    );
    const panel = page.getByTestId("page-content");
    const react: TwinValues = {
      heading: clean(await panel.locator(".lb").first().textContent()),
      stats: (
        await page.getByTestId("pack-stats").locator(".big").allTextContents()
      ).map(clean),
      message: clean(await page.getByTestId("module-message").textContent()),
      fill:
        (await page
          .getByRole("button", { name: "Module 1" })
          .locator("polygon")
          .nth(2)
          .getAttribute("fill")) ?? "",
      legend: (
        await page.getByLabel("Colour legend").locator("span").allTextContents()
      ).map(clean),
    };
    expect(legacy.stats).toHaveLength(4);
    expect(react).toEqual(legacy);
  });
}

interface SimValues {
  labels: string[];
  cycles: string;
  delta: string;
  stats: string[];
  assumptions: string;
  current: string[];
  baseline: string[];
}

/** Legacy slider ids (`i` + prototype key) and the React slider names. */
const SIM_SLIDERS = {
  T: /^Temperature/,
  C: /^Charge rate/,
  D: /^Depth of discharge/,
  N: /^Cycles to simulate/,
  S: /^Initial SOH/,
  E: /^End-of-life SOH/,
} as const;

/** Defaults plus five presets: hot and fast, cool and gentle, extreme, never-EOL, already at EOL. */
const PRESETS: Partial<Record<keyof typeof SIM_SLIDERS, number>>[] = [
  {},
  { T: 35, C: 2, D: 100 },
  { T: 15, C: 0.5, D: 60, N: 1000 },
  { T: 45, C: 3, D: 100, N: 1500, S: 70, E: 60 },
  { T: 5, C: 0.5, D: 20, N: 100, S: 100, E: 60 },
  { S: 80, E: 80 },
];

for (const preset of PRESETS) {
  test(`Simulator ${JSON.stringify(preset)} matches the legacy prototype`, async ({
    page,
  }) => {
    await page.goto(`${LEGACY_URL}#sim`);
    await page.locator("#schart canvas").first().waitFor();
    await page.evaluate((p) => {
      for (const [k, v] of Object.entries(p)) {
        const input = document.getElementById(`i${k}`) as HTMLInputElement;
        input.value = String(v);
        input.dispatchEvent(new Event("input"));
      }
    }, preset);
    const legacy: SimValues = await page.evaluate(() => {
      const text = (e: Element | null | undefined) =>
        (e?.textContent ?? "").replace(/\s+/g, " ").trim();
      const res = document.getElementById("sres") as HTMLElement;
      const chart = (
        window as unknown as {
          echarts: {
            getInstanceByDom(el: Element | null): {
              getOption(): { series: { data: [number, number][] }[] };
            };
          };
        }
      ).echarts
        .getInstanceByDom(document.getElementById("schart"))
        .getOption();
      return {
        labels: ["T", "C", "D", "N", "S", "E"].map((k) =>
          text(document.getElementById(`o${k}`)),
        ),
        cycles: text(res.querySelector(".big")),
        // Approved deviation: when both sides start at EOL the prototype printed "(NaN%)".
        delta: text(res.querySelector(":scope > p")).replace("(NaN%)", "(n/a)"),
        stats: [...res.querySelectorAll(".stats2 b")].map(text),
        assumptions: text(res.querySelector("p.mu")),
        current: (chart.series[1]?.data ?? []).map(([, y]) => y.toFixed(2)),
        baseline: (chart.series[0]?.data ?? []).map(([, y]) => y.toFixed(2)),
      };
    });

    await page.goto("/simulator");
    await settled(page);
    for (const [k, v] of Object.entries(preset))
      await page
        .getByRole("slider", {
          name: SIM_SLIDERS[k as keyof typeof SIM_SLIDERS],
        })
        .fill(String(v));
    const results = page.getByTestId("sim-results");
    // Wait for the debounced simulation of exactly these parameters.
    const expected = { T: 25, C: 1, D: 80, N: 600, S: 86.1, E: 80, ...preset };
    await expect(results).toHaveAttribute(
      "data-params",
      [
        expected.T,
        expected.C,
        expected.D,
        expected.N,
        expected.S,
        expected.E,
      ].join("|"),
    );
    const rows = await page
      .getByRole("table", {
        name: "Scenario SOH trajectories (%)",
        includeHidden: true,
      })
      .locator("tbody tr")
      .evaluateAll((trs) =>
        trs.map((tr) =>
          [...tr.querySelectorAll("td")].map((td) => td.textContent),
        ),
      );
    const react: SimValues = {
      labels: await Promise.all(
        [
          "temp_c",
          "c_rate",
          "dod_pct",
          "horizon_cycles",
          "start_soh_pct",
          "eol_pct",
        ].map(async (k) =>
          clean(await page.getByTestId(`value-${k}`).textContent()),
        ),
      ),
      cycles: clean(await page.getByTestId("cycles-to-eol").textContent()),
      delta: clean(await page.getByTestId("delta").textContent()),
      stats: (await results.locator("b").allTextContents()).map(clean),
      assumptions: clean(await page.getByTestId("assumptions").textContent()),
      current: rows.map((r) => r[2] ?? ""),
      baseline: rows.map((r) => r[1] ?? ""),
    };
    expect(legacy.stats).toHaveLength(4);
    expect(react).toEqual(legacy);
  });
}
