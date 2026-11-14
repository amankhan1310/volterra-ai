import { fireEvent, screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { chartByLabel, lastOption } from "../../test/echartsMock";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";

const content = () => screen.findByTestId("page-content");

describe("Anomaly Detection against the recorded API", () => {
  it("shows the prototype's counts, severity rule and provenance", async () => {
    renderApp("/anomalies");
    const summary = await content();
    expect(screen.getByTestId("events-total").textContent).toBe("8");
    expect(screen.getByTestId("severity-counts").textContent).toBe(
      "2 high · 6 medium",
    );
    expect(summary.textContent).toContain(
      "High = |z| above 6, medium = 3.5 to 6.",
    );
    expect(
      within(summary)
        .getByText("Detected: robust z-score (v1)")
        .getAttribute("data-provenance"),
    ).toBe("fitted");
    expect(
      screen.getByRole("heading", { name: "Anomaly Detection" }),
    ).toBeTruthy();
  });

  it("draws every event on its lane, with a tooltip on keyboard focus", async () => {
    renderApp("/anomalies");
    await content();
    const timeline = screen.getByRole("group", { name: "Anomaly timeline" });
    const dots = within(timeline).getAllByTestId("timeline-event");
    expect(dots.map((d) => d.getAttribute("data-cycle"))).toEqual([
      "170",
      "130",
      "271",
      "125",
      "127",
      "254",
      "315",
      "319",
    ]);
    const dot = within(timeline).getByRole("img", {
      name: "Cycle 130: Voltage dip/spike, high severity",
    });
    expect(dot.getAttribute("tabindex")).toBe("0");
    expect(dot.getAttribute("fill")).toBe("var(--rd)");
    expect(timeline.textContent).toContain("cycle 319");
    fireEvent.focus(dot);
    expect(timeline.querySelector("g[aria-hidden='true']")?.textContent).toBe(
      "Cycle 130: Voltage dip/spike, high severity",
    );
    fireEvent.blur(dot);
    expect(timeline.querySelector("g[aria-hidden='true']")).toBeNull();
    fireEvent.mouseEnter(dots[0] as Element);
    expect(
      timeline.querySelector("g[aria-hidden='true']")?.textContent,
    ).toContain("Cycle 170");
    fireEvent.mouseLeave(dots[0] as Element);
    expect(timeline.querySelector("g[aria-hidden='true']")).toBeNull();
  });

  it("plots temperature and voltage with their flagged points and data tables", async () => {
    renderApp("/anomalies");
    await content();
    const temp = await screen.findByRole("img", {
      name: "Temperature per cycle with 1 flagged events.",
    });
    expect(temp).toBeTruthy();
    expect(
      screen.getByRole("img", {
        name: "Voltage per cycle with 2 flagged events.",
      }),
    ).toBeTruthy();
    const volt = lastOption(chartByLabel(/^Voltage per cycle/)) as {
      series: { name: string; data: [number, number][] }[];
    };
    expect(volt.series.map((s) => s.name)).toEqual(["Voltage (V)", "Flagged"]);
    expect(volt.series[1]?.data.map(([c]) => c)).toEqual([130, 271]);
    const table = screen.getByRole("table", {
      name: "Voltage per cycle with flagged events (V)",
    });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(fixtures.cycles.items.length);
    const flagged = rows
      .map((r) =>
        within(r)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      )
      .filter((cells) => cells[2] === "Yes");
    expect(flagged).toEqual([
      ["130", "3.516", "Yes"],
      ["271", "3.489", "Yes"],
    ]);
  });

  it("lists the detected events with the prototype's formatting", async () => {
    renderApp("/anomalies");
    await content();
    const table = screen.getByTestId("events-table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(8);
    const cells = (i: number) =>
      within(rows[i] as HTMLElement)
        .getAllByRole("cell")
        .map((c) => c.textContent);
    expect(cells(0)).toEqual([
      "125",
      "Irregular capacity step",
      "-0.33 % resid.",
      "-0.32 to 0.32",
      "Medium",
    ]);
    expect(cells(2)).toEqual([
      "130",
      "Voltage dip/spike",
      "3.516 V",
      "3.60 to 3.78",
      "High",
    ]);
    expect(cells(3)).toEqual([
      "170",
      "Temperature excursion",
      "36.40 °C",
      "14.38 to 34.86",
      "Medium",
    ]);
    expect(
      screen.getByText(/^Flagged when a value sits more than/).textContent,
    ).toBe(
      "Flagged when a value sits more than 3.5 robust standard deviations from the median.",
    );
    expect(
      screen.getByLabelText("Detected events table, scrolls sideways").tabIndex,
    ).toBe(0);
  });

  it("keeps the limits collapsed, in plain language without defect codes (U3, D4)", async () => {
    renderApp("/anomalies");
    await content();
    const details = screen.getByText("About these results").closest("details");
    expect(details?.open).toBe(false);
    expect(details?.textContent).toContain("slow periodic pattern");
    expect(details?.textContent).toContain("reads later cycles");
    expect(details?.textContent).not.toMatch(/\bF\d\b/);
  });
});

describe("Anomaly Detection data states", () => {
  it("shows the prototype's empty state when nothing is flagged", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/anomalies", () =>
        HttpResponse.json({
          ...fixtures.anomalies,
          events: [],
          summary: { total: 0, high: 0, medium: 0 },
        }),
      ),
    );
    renderApp("/anomalies");
    await content();
    expect(screen.getByTestId("events-total").textContent).toBe("0");
    expect(screen.getByTestId("events-total").style.color).toBe("var(--gr)");
    expect(
      screen.getByText(
        "No anomalies at this threshold. Lower the threshold or load more data to keep monitoring.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("events-table")).toBeNull();
    expect(screen.queryAllByTestId("timeline-event")).toHaveLength(0);
  });

  it("shows the API error with a retry when a request fails", async () => {
    let fail = true;
    server.use(
      http.get("*/api/v1/batteries/:id/cycles", () =>
        fail
          ? apiError(
              503,
              "database_unavailable",
              "The database is not configured",
            )
          : HttpResponse.json(fixtures.cycles),
      ),
    );
    const { user } = renderApp("/anomalies");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await content()).toBeTruthy();
  });

  it("shows a skeleton while loading", async () => {
    renderApp("/anomalies");
    expect(
      await screen.findByRole("status", { name: "Loading anomaly detection" }),
    ).toBeTruthy();
    await content();
  });
});
