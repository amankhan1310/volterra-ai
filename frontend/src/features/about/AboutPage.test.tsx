import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { Battery } from "../../api/types";
import { getPage } from "../../app/pages";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";
import { dataText, methodText } from "./AboutPage";
import { LIMITATIONS } from "./limitations";

const content = () => screen.findByTestId("page-content");
const battery = fixtures.batteries.items[0] as Battery;

describe("About text helpers", () => {
  it("states the prototype's data and method from the battery record and fit range", () => {
    expect(dataText(battery)).toBe(
      "320 seeded synthetic cycles of a 2.0 Ah cell. Reproducible, not measured from any vehicle.",
    );
    expect(methodText(battery, fixtures.summary)).toBe(
      "SOH = capacity ÷ 2 Ah. RUL from a linear fit over the last 120 cycles, scored by a time-ordered backtest. Anomalies by median/MAD z-score. Simulator uses assumed coefficients.",
    );
  });

  it("does not call measured data synthetic", () => {
    expect(
      dataText({
        ...battery,
        is_synthetic: false,
        cycle_count: 168,
        nominal_capacity_ah: 2,
        dataset_name: "NASA PCoE B0005",
      }),
    ).toBe("168 measured cycles of a 2.0 Ah cell from NASA PCoE B0005.");
  });
});

describe("known limitations", () => {
  it("lists F1–F8 once each, in order", () => {
    expect(LIMITATIONS.map((l) => l.code)).toEqual([
      "F1",
      "F2",
      "F3",
      "F4",
      "F5",
      "F6",
      "F7",
      "F8",
    ]);
  });

  it("agrees with the codes the API reports on each response", () => {
    const shownOn = (code: string) =>
      LIMITATIONS.find((l) => l.code === code)?.pages ?? [];
    for (const code of fixtures.anomalies.known_issues)
      expect(shownOn(code)).toContain("anom");
    for (const code of fixtures.advisor.known_issues)
      expect(shownOn(code)).toContain("advisor");
    for (const code of fixtures.simulateDefault.known_issues)
      expect(shownOn(code)).toContain("sim");
  });

  it("contains no numbers that could drift from the API's results", () => {
    for (const l of LIMITATIONS) {
      // Only the fixed method constants (1.2× rule, 5000-cycle horizon) may appear.
      const numbers = `${l.title} ${l.text}`.match(/\d+(\.\d+)?/g) ?? [];
      expect(numbers.every((n) => ["1.2", "5000", "0"].includes(n))).toBe(true);
    }
  });
});

describe("About against the recorded API", () => {
  it("shows the prototype's cards with live values", async () => {
    renderApp("/about");
    await content();
    expect(
      screen.getByRole("heading", { level: 1, name: "About" }),
    ).toBeTruthy();
    expect(screen.getByTestId("about-data").textContent).toBe(
      dataText(battery),
    );
    expect(screen.getByTestId("about-method").textContent).toContain(
      "linear fit over the last 120 cycles",
    );
    expect(screen.getByTestId("about-ev").textContent).toContain(
      "does not replace a Battery Management System",
    );
    expect(screen.getByTestId("about-definitions").textContent).toContain(
      "is not a guaranteed replacement date",
    );
    expect(screen.getByTestId("about-not-included").textContent).not.toContain(
      "Python backend",
    );
    expect(
      within(screen.getByTestId("page-content"))
        .getByText("Simulated")
        .getAttribute("data-provenance"),
    ).toBe("simulated");
  });

  it("lists the limitations with codes and links to the pages that show them (D4)", async () => {
    renderApp("/about");
    await content();
    const list = screen.getByRole("list", {
      name: "Known limitations of the current (v1) methods",
    });
    const items = within(list).getAllByTestId("limitation");
    expect(items).toHaveLength(8);
    expect(items[0]?.textContent).toContain("F1");
    expect(items[0]?.textContent).toContain("Temperature spikes can be missed");
    const f4 = within(items[3] as HTMLElement).getAllByRole("link");
    expect(f4.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Overview", getPage("overview").path],
      ["What-If Simulator", getPage("sim").path],
    ]);
    expect(
      within(items[7] as HTMLElement)
        .getByRole("link")
        .getAttribute("href"),
    ).toBe("/advisor");
  });

  it("follows a limitation's link to its page", async () => {
    const { user, router } = renderApp("/about");
    await content();
    await user.click(
      within(screen.getAllByTestId("limitation")[7] as HTMLElement).getByRole(
        "link",
        { name: "Charging Advisor" },
      ),
    );
    expect(router.state.location.pathname).toBe("/advisor");
  });
});

describe("About data states", () => {
  it("shows the API error with a retry", async () => {
    let fail = true;
    server.use(
      http.get("*/api/v1/batteries/:id/summary", () =>
        fail
          ? apiError(
              503,
              "database_unavailable",
              "The database is not configured",
            )
          : HttpResponse.json(fixtures.summary),
      ),
    );
    const { user } = renderApp("/about");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Database unavailable");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await content()).toBeTruthy();
  });

  it("shows a skeleton while loading", async () => {
    renderApp("/about");
    expect(
      await screen.findByRole("status", {
        name: "Loading project information",
      }),
    ).toBeTruthy();
    await content();
  });
});
