/**
 * Number parity with the frozen prototype (Phase 4 Definition of Done): every value the legacy
 * Overview shows must appear identically in React. The prototype computes in the browser; React
 * shows what the API returns, so this checks the whole chain (Python port → API → UI).
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
