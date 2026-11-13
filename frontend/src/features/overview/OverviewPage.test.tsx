import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { Summary } from "../../api/types";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { chartByLabel, lastOption } from "../../test/echartsMock";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp, renderWithProviders } from "../../test/render";
import { OverviewPage } from "./OverviewPage";

interface Series {
  name: string;
  data: [number, number][];
}
interface Option {
  series: Series[];
  dataZoom: { startValue: number }[];
}

const TIMELINE = /^SOH over 320 observed cycles/;
const TELEMETRY = /per cycle, \d+ flagged points\.$/;

async function loaded() {
  return screen.findByTestId("page-content");
}

describe("Overview against the recorded API", () => {
  it("shows the prototype's hero values", async () => {
    renderApp("/overview");
    const hero = await loaded();
    expect(
      within(hero).getByRole("img", { name: "State of health 86.1 percent" }),
    ).toBeTruthy();
    expect(within(hero).getByText("Good")).toBeTruthy();
    expect(hero.textContent).toContain(
      "The estimate is a straight-line fit over the latest 120 cycles of the simulated dataset. Fade has accelerated over the cell’s life, so the true remaining life may be shorter than a linear fit implies.",
    );
    expect(within(hero).getByTestId("rul").textContent).toBe(
      "113cycles to 80% SOH",
    );
    expect(hero.textContent).toContain("0.054 %/cycle");
    expect(hero.textContent).toContain("95% fit interval");
    expect(hero.textContent).toContain("111–114 cycles");
    expect(hero.textContent).toContain("0.58 SOH pts");
    expect(hero.textContent).toContain(
      "Straight-line forecast scored on the held-out final 100 cycles.",
    );
    expect(hero.textContent).toContain(
      "inner ring: life used to 80% threshold",
    );
    const tags = [...hero.querySelectorAll("[data-provenance]")].map((t) => [
      t.getAttribute("data-provenance"),
      t.textContent,
    ]);
    expect(tags).toEqual([
      ["simulated", "Simulated data"],
      ["fitted", "Fitted: linear trend"],
      ["predicted", "Predicted"],
    ]);
    // No EOL chip while the threshold is the default (U1).
    expect(screen.queryByText(/set in the Simulator/)).toBeNull();
  });

  it("animates the arcs from empty to SOH and life used", async () => {
    renderApp("/overview");
    const hero = await loaded();
    const outer = within(hero).getByTestId("gauge-outer");
    const inner = within(hero).getByTestId("gauge-inner");
    await waitFor(() => {
      expect(Number(outer.getAttribute("stroke-dashoffset"))).toBeCloseTo(
        2 * Math.PI * 118 * (1 - 86.08941987140724 / 100),
      );
    });
    expect(Number(inner.getAttribute("stroke-dashoffset"))).toBeCloseTo(
      2 * Math.PI * 96 * (1 - 0.6955290064296378),
    );
  });

  it("shows the six KPI cards with the prototype's values and notes", async () => {
    renderApp("/overview");
    await loaded();
    const text = (
      await screen.findByText("1 excursions flagged in history")
    ).closest("main")?.textContent;
    for (const expected of [
      "1.717Ah",
      "of 2.0 Ah reference",
      "26.4°C",
      "3.66V",
      "drifting down with age",
      "320",
      "seeded, reproducible",
      "last 120 cycles",
      "2 high severity",
    ])
      expect(text).toContain(expected);
    expect(
      screen.getByText("Latest cycle discharge capacity (simulated)."),
    ).toBeTruthy();
    const anomalies = screen.getByText("2 high severity").parentElement;
    expect(anomalies?.querySelector(".big")?.getAttribute("style")).toContain(
      "var(--am)",
    );
  });

  it("lists the four API insights with their labels", async () => {
    renderApp("/overview");
    expect(await screen.findByText("Intelligence insights")).toBeTruthy();
    for (const insight of fixtures.insights.insights)
      expect(screen.getByText(insight.text)).toBeTruthy();
    for (const label of ["Observation", "Watch", "Note", "Model"])
      expect(screen.getByText(label)).toBeTruthy();
    expect(
      screen.getByText("Rule-based findings from the analysis API"),
    ).toBeTruthy();
  });

  it("draws the timeline and switches between the full range and the last 120 cycles", async () => {
    const { user } = renderApp("/overview");
    await screen.findByRole("img", { name: TIMELINE });
    const chart = chartByLabel(TIMELINE);
    let option = lastOption(chart) as Option;
    expect(option.series.map((s) => s.name)).toEqual([
      "Observed (simulated)",
      "Forecast (linear fit)",
    ]);
    expect(option.dataZoom[0]?.startValue).toBe(0);
    const range = screen.getByRole("group", { name: "Timeline range" });
    await user.click(within(range).getByRole("button", { name: "Last 120" }));
    option = lastOption(chart) as Option;
    expect(option.dataZoom[0]?.startValue).toBe(200);
    expect(
      within(range)
        .getByRole("button", { name: "Last 120" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    await user.click(within(range).getByRole("button", { name: "Full" }));
    expect((lastOption(chart) as Option).dataZoom[0]?.startValue).toBe(0);
    expect(
      screen.getByRole("table", { name: "Degradation timeline data (SOH, %)" }),
    ).toBeTruthy();
  });

  it("opens the telemetry explorer on temperature and switches channels", async () => {
    const { user } = renderApp("/overview");
    expect(
      await screen.findByRole("img", {
        name: "Temperature per cycle, 1 flagged points.",
      }),
    ).toBeTruthy();
    let option = lastOption(chartByLabel(TELEMETRY)) as Option;
    expect(option.series.map((s) => s.name)).toEqual([
      "Temperature (°C)",
      "Flagged",
    ]);
    const channels = screen.getByRole("group", { name: "Telemetry channel" });
    await user.click(within(channels).getByRole("button", { name: "Voltage" }));
    expect(
      screen.getByRole("img", { name: "Voltage per cycle, 2 flagged points." }),
    ).toBeTruthy();
    await user.click(
      within(channels).getByRole("button", { name: "Capacity" }),
    );
    option = lastOption(chartByLabel(TELEMETRY)) as Option;
    expect(option.series.map((s) => s.name)).toEqual(["Capacity (Ah)"]);
    const table = screen.getByRole("table", {
      name: "Capacity per cycle (Ah)",
    });
    expect(within(table).getAllByRole("row")).toHaveLength(321);
  });

  it("explains the limits of these results in a collapsed section (U3)", async () => {
    renderApp("/overview");
    const summary = await screen.findByText("About these results");
    const details = summary.closest("details");
    expect(details?.open).toBe(false);
    expect(details?.textContent).toContain("backtest error of 0.58 SOH points");
    expect(details?.textContent).not.toMatch(/\bF\d\b/);
  });

  it("follows the shared EOL threshold and shows the chip when it differs (D1, U1)", async () => {
    const requested: string[] = [];
    server.events.on("request:start", ({ request }) => {
      const url = new URL(request.url);
      if (url.pathname.endsWith("/summary"))
        requested.push(url.searchParams.get("eol_pct") ?? "");
    });
    function MoveEol() {
      const draft = useScenarioDraft();
      return (
        <button
          type="button"
          onClick={() => {
            draft.setParam("eol_pct", 70);
          }}
        >
          EOL 70
        </button>
      );
    }
    const { user } = renderWithProviders(
      <>
        <MoveEol />
        <OverviewPage />
      </>,
    );
    await loaded();
    await user.click(screen.getByRole("button", { name: "EOL 70" }));
    await waitFor(() => {
      expect(screen.getByTestId("rul").textContent).toBe(
        "298cycles to 70% SOH",
      );
    });
    expect(
      screen.getByText("EOL threshold 70% · set in the Simulator"),
    ).toBeTruthy();
    expect(screen.getByTestId("page-content").textContent).toContain(
      "295–301 cycles",
    );
    expect(
      screen.getByText("inner ring: life used to 70% threshold"),
    ).toBeTruthy();
    expect(requested).toEqual(["80", "70"]);
    server.events.removeAllListeners();
  });

  it("quotes SOH and RUL in the Run analysis toast, as a reload", async () => {
    const { user } = renderApp("/overview");
    await loaded();
    await screen.findByText("v1");
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(
      await screen.findByText(
        "Analysis results reloaded from the API (synthetic-v1, algorithm v1): SOH 86.1%, RUL 113 cycles. No model was retrained.",
      ),
    ).toBeTruthy();
  });
});

describe("Overview data states", () => {
  it("shows a skeleton per card while loading", async () => {
    renderApp("/overview");
    expect(
      await screen.findByRole("status", { name: "Loading battery health" }),
    ).toBeTruthy();
    await loaded();
  });

  it("keeps the other cards when one request fails, and retries it", async () => {
    let fail = true;
    server.use(
      http.get("*/api/v1/batteries/:id/insights", () =>
        fail
          ? apiError(
              503,
              "database_unavailable",
              "The database is not configured",
            )
          : HttpResponse.json(fixtures.insights),
      ),
    );
    const { user } = renderApp("/overview");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    expect(alert.textContent).toContain("Error code: database_unavailable");
    expect(await loaded()).toBeTruthy();
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Intelligence insights")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports a failed simulator configuration instead of loading forever", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/simulator", () =>
        apiError(500, "internal_error", "Simulator configuration failed"),
      ),
    );
    renderApp("/overview");
    const alerts = await screen.findAllByRole("alert");
    expect(alerts[0]?.textContent).toContain("Simulator configuration failed");
  });

  it("shows n/a and dashes for missing or non-finite results", async () => {
    const summary: Summary = {
      ...fixtures.summary,
      rul: { ...fixtures.summary.rul, point: null, lower: null, upper: null },
      fade_rate: {
        ...fixtures.summary.fade_rate,
        value: "NaN" as unknown as number,
      },
      acceleration: {
        ...fixtures.summary.acceleration,
        accelerated: false,
        note: "",
      },
    };
    server.use(
      http.get("*/api/v1/batteries/:id/summary", () =>
        HttpResponse.json(summary),
      ),
    );
    renderApp("/overview");
    const hero = await loaded();
    expect(within(hero).getByTestId("rul").textContent).toBe(
      "n/acycles to 80% SOH",
    );
    expect(hero.textContent).toContain("––– cycles");
    expect(hero.textContent).toContain("n/a %/cycle");
    expect(hero.textContent).not.toContain("accelerated");
  });

  it("labels measured data as measured (real datasets arrive in Phase 6)", async () => {
    // Constructed from the recorded responses: only the provenance fields change.
    const context = {
      ...fixtures.summary.context,
      data_provenance: "measured" as const,
      is_synthetic: false,
    };
    server.use(
      http.get("*/api/v1/batteries/:id/summary", () =>
        HttpResponse.json({
          ...fixtures.summary,
          context,
          soh_now: { ...fixtures.summary.soh_now, value: null },
          life_used_fraction: {
            ...fixtures.summary.life_used_fraction,
            value: null,
          },
          anomalies: { total: 0, high: 0, medium: 0 },
        }),
      ),
      http.get("*/api/v1/batteries/:id/cycles", () =>
        HttpResponse.json({ ...fixtures.cycles, provenance: "measured" }),
      ),
      http.get("*/api/v1/batteries/:id/forecast", () =>
        HttpResponse.json({
          ...fixtures.forecast,
          observed: { ...fixtures.forecast.observed, provenance: "measured" },
        }),
      ),
    );
    renderApp("/overview");
    const hero = await loaded();
    expect(hero.textContent).toContain("cycles of the measured dataset.");
    expect(within(hero).getByText("Measured data")).toBeTruthy();
    expect(
      within(hero).getByRole("img", { name: "State of health n/a percent" }),
    ).toBeTruthy();
    expect(
      await screen.findByText("Latest cycle discharge capacity (measured)."),
    ).toBeTruthy();
    expect(screen.getByText("in the dataset")).toBeTruthy();
    expect(
      await screen.findByText("Observed (measured) vs. linear forecast"),
    ).toBeTruthy();
    const anomalies = screen.getByText("0 high severity").parentElement;
    expect(anomalies?.querySelector(".big")?.getAttribute("style")).toContain(
      "var(--tx)",
    );
  });
});
