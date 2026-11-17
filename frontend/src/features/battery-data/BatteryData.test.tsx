import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";

const CALCE = "calce-test:CS2_T";
const NASA = "nasa-test:B0005";

/** URLs the app requested during a test (to prove gated pages never ask for analytics). */
let requested: string[] = [];
const onRequest = ({ request }: { request: Request }) => {
  requested.push(new URL(request.url).pathname);
};
beforeEach(() => {
  requested = [];
  server.events.on("request:start", onRequest);
});
afterEach(() => {
  server.events.removeListener("request:start", onRequest);
});

const analyticsRequests = (id: string) =>
  requested.filter(
    (p) =>
      p.startsWith(`/api/v1/batteries/${id}/`) &&
      !p.endsWith("/cycles") &&
      !p.includes("/samples"),
  );

const text = (el: Element) => el.textContent;

describe("battery selection (?battery=, decision D11)", () => {
  it("opens the synthetic reference battery when no battery is given", async () => {
    renderApp("/battery-data");
    expect(text(await screen.findByTestId("data-battery"))).toBe("SYN-001");
    expect(await screen.findByTestId("samples-synthetic")).toBeTruthy();
    const select = screen.getByRole<HTMLSelectElement>("combobox", {
      name: "Battery",
    });
    expect(select.selectedOptions[0]?.textContent).toBe(
      "SYN-001 · 320 cycles · synthetic",
    );
  });

  it("explains why the analytics are unavailable and never requests them", async () => {
    renderApp(`/overview?battery=${CALCE}`);
    expect(
      await screen.findByText("Analytics are not available for CS2_T"),
    ).toBeTruthy();
    expect(text(screen.getByTestId("limitation-message"))).toBe(
      fixtures.calce.analysis.message,
    );
    const context = text(screen.getByLabelText("Data context"));
    expect(context).toContain("Dataset calce-test");
    expect(context).toContain("Measured data");
    expect(
      within(
        screen.getByTestId("limitation-message").parentElement ?? document.body,
      )
        .getByRole("link", { name: "Battery Data" })
        .getAttribute("href"),
    ).toBe(`/battery-data?battery=${encodeURIComponent(CALCE)}`);
    expect(analyticsRequests(fixtures.calce.id)).toEqual([]);
  });

  it.each([
    ["/simulator", CALCE, "Analytics are not available for CS2_T"],
    ["/anomalies", NASA, "Analytics are not available for B0005"],
    ["/advisor", NASA, "Analytics are not available for B0005"],
    ["/digital-twin", CALCE, "This view is not available for CS2_T"],
  ])("%s for %s shows the limitation state", async (path, key, title) => {
    renderApp(`${path}?battery=${key}`);
    expect(await screen.findByText(title)).toBeTruthy();
    for (const b of [fixtures.calce, fixtures.nasa])
      expect(analyticsRequests(b.id)).toEqual([]);
  });

  it("reports an unknown battery instead of silently showing another", async () => {
    renderApp("/overview?battery=nope:X1");
    expect(await screen.findByText("Battery not found")).toBeTruthy();
    expect(screen.getByText("nope:X1")).toBeTruthy();
  });

  it("switching battery updates the URL and keeps it while navigating", async () => {
    const { router, user } = renderApp("/overview");
    const select = await screen.findByRole("combobox", { name: "Battery" });
    await user.selectOptions(select, CALCE);
    expect(router.state.location.search).toBe(
      `?battery=${encodeURIComponent(CALCE)}`,
    );
    expect(
      await screen.findByText("Analytics are not available for CS2_T"),
    ).toBeTruthy();
    await user.click(
      within(screen.getByRole("navigation", { name: "Main" })).getByRole(
        "link",
        { name: "Digital Twin" },
      ),
    );
    expect(router.state.location.pathname).toBe("/digital-twin");
    expect(router.state.location.search).toBe(
      `?battery=${encodeURIComponent(CALCE)}`,
    );
    expect(
      await screen.findByText("This view is not available for CS2_T"),
    ).toBeTruthy();
    // Back to the reference battery from the limitation state.
    await user.click(
      screen.getByRole("link", { name: "synthetic reference battery" }),
    );
    await waitFor(() => {
      expect(router.state.location.search).toBe(
        "?battery=synthetic-v1%3ASYN-001",
      );
    });
  });
});

describe("Battery Data page (measured data)", () => {
  it("shows the source notes, missing channels and downsampled samples", async () => {
    const { user } = renderApp(`/battery-data?battery=${CALCE}`);
    expect(text(await screen.findByTestId("data-battery"))).toBe("CS2_T");
    expect(text(screen.getByTestId("data-analysis"))).toContain(
      "Analytics unavailable",
    );
    const notes = screen.getByRole("list", { name: "Source notes" });
    expect(
      within(notes).getByText("earlier_history_not_converted"),
    ).toBeTruthy();
    expect(text(await screen.findByTestId("data-not-measured"))).toContain(
      "temperature",
    );
    const cycle = screen.getByRole("spinbutton", { name: "Cycle number" });
    await user.clear(cycle);
    await user.type(cycle, "7");
    expect(text(await screen.findByTestId("samples-note"))).toBe(
      "Cycle 7: 1500 of 5001 measured samples (evenly downsampled for the chart; first and last kept).",
    );
  });

  it("reports cycles that are not in the data and samples without a value", async () => {
    const { user } = renderApp(`/battery-data?battery=${NASA}`);
    const cycle = await screen.findByRole("spinbutton", {
      name: "Cycle number",
    });
    await user.clear(cycle);
    await user.type(cycle, "1");
    expect(text(await screen.findByRole("alert"))).toBe(
      "Cycle 1 is not in this battery's data (cycles 0–2, with gaps).",
    );
    await user.clear(cycle);
    await user.type(cycle, "0");
    expect(text(await screen.findByTestId("samples-note"))).toBe(
      "Cycle 0: 4 of 4 measured samples. 1 samples have no voltage value.",
    );
  });
});

describe("capacity degradation and SOH (measured capacity only)", () => {
  it("analyses a cell without temperature against its rated capacity", async () => {
    renderApp(`/battery-data?battery=${CALCE}`);
    const panel = await screen.findByTestId("capacity-panel");
    const reference = await within(panel).findByTestId("capacity-reference");
    const calce = fixtures.capacityCalce;
    expect(calce.reference?.capacity_ah).toBe(1.1);
    expect(text(reference)).toContain("SOH reference: 1.10 Ah");
    expect(text(reference)).toContain("not the first measurement");
    expect(text(within(panel).getByTestId("capacity-trend"))).toContain(
      `over ${String(calce.trend?.cycles)} cycles`,
    );
    expect(text(panel)).toContain("needs no temperature");
    // The full analytics stay refused, with the API's reason.
    expect(text(panel)).toContain(calce.full_analytics.message ?? "");
  });

  it("states that a short NASA recording supports no trend", async () => {
    renderApp(`/battery-data?battery=${NASA}`);
    const panel = await screen.findByTestId("capacity-panel");
    await within(panel).findByTestId("capacity-reference");
    expect(within(panel).queryByTestId("capacity-trend")).toBeNull();
    const limits = within(panel).getByRole("list", { name: "Limitations" });
    expect(text(limits)).toContain("at least 10 usable cycles");
  });

  it("follows the selected battery without stale values", async () => {
    const { user } = renderApp(`/battery-data?battery=${CALCE}`);
    const panel = await screen.findByTestId("capacity-panel");
    await within(panel).findByTestId("capacity-trend");
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Battery" }),
      "synthetic-v1:SYN-001",
    );
    await waitFor(() => {
      expect(text(screen.getByTestId("capacity-reference"))).toContain(
        "SOH reference: 2.00 Ah",
      );
    });
    expect(text(screen.getByTestId("capacity-reference"))).toContain(
      "Nominal capacity the synthetic generator",
    );
  });
});
