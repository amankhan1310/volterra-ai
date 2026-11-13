import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import type { Scenario } from "../../api/types";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { chartByLabel, lastOption } from "../../test/echartsMock";
import {
  apiError,
  fixtures,
  resetScenarioStore,
  server,
  storedScenarios,
} from "../../test/msw";
import { renderApp, renderWithProviders } from "../../test/render";
import { SimulatorPage } from "./SimulatorPage";

const results = () => screen.findByTestId("sim-results");
const slider = (name: RegExp) =>
  screen.getByRole<HTMLInputElement>("slider", { name });
const CHART = /^Simulated SOH over/;
const seriesNames = () =>
  (
    lastOption(chartByLabel(CHART)) as { series: { name: string }[] }
  ).series.map((s) => s.name);

function saved(n: number): Scenario[] {
  return Array.from({ length: n }, (_, i) => ({
    ...fixtures.scenario,
    id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`,
    name: `Scenario ${String(i + 1)}`,
  }));
}

function recordSimulations(): string[] {
  const temps: string[] = [];
  server.events.on("request:start", ({ request }) => {
    if (new URL(request.url).pathname.endsWith("/simulate"))
      void request
        .clone()
        .json()
        .then((b: { params: { temp_c: number } }) => {
          temps.push(String(b.params.temp_c));
        });
  });
  return temps;
}

describe("What-If Simulator against the recorded API", () => {
  it("shows the API's sliders, defaults and the prototype's default results", async () => {
    renderApp("/simulator");
    const r = await results();
    for (const [name, value] of [
      [/^Temperature/, "25 °C"],
      [/^Charge rate/, "1 C"],
      [/^Depth of discharge/, "80 %"],
      [/^Cycles to simulate/, "600"],
      [/^Initial SOH/, "86.1 %"],
      [/^End-of-life SOH/, "80 %"],
    ] as const)
      expect(slider(name).labels?.[0]?.textContent).toContain(value);
    expect(slider(/^Temperature/).min).toBe("5");
    expect(slider(/^Temperature/).max).toBe("45");
    expect(slider(/^Charge rate/).step).toBe("0.1");
    expect(within(r).getByTestId("cycles-to-eol").textContent).toBe("106");
    expect(within(r).getByTestId("delta").textContent).toBe(
      "0 cycles vs baseline (0%)",
    );
    for (const v of ["40.7%", "0.054 %/cyc", "106", "SOH after 600"])
      expect(r.textContent).toContain(v);
    expect(within(r).getByTestId("assumptions").textContent).toBe(
      "Base fade 0.054 %/cycle fitted from the last 120 simulated cycles; scaling coefficients are assumed.",
    );
    expect(
      within(r).getByText("Simulated estimate").getAttribute("data-provenance"),
    ).toBe("simulated");
    expect(
      await screen.findByText(
        "Adjust the controls, then save a scenario to overlay it on the chart.",
      ),
    ).toBeTruthy();
    expect(seriesNames()).toEqual(["Baseline", "Current"]);
    expect(screen.getByText(/^Model: SOH\(n\)/)).toBeTruthy();
    expect(
      screen.getByRole("table", {
        name: "Scenario SOH trajectories (%)",
        hidden: true,
      }),
    ).toBeTruthy();
  });

  it("debounces slider changes and shows the new result", async () => {
    const temps = recordSimulations();
    renderApp("/simulator");
    await results();
    fireEvent.change(slider(/^Temperature/), { target: { value: "30" } });
    fireEvent.change(slider(/^Temperature/), { target: { value: "35" } });
    expect(slider(/^Temperature/).labels?.[0]?.textContent).toContain("35 °C");
    await waitFor(() => {
      expect(screen.getByTestId("cycles-to-eol").textContent).toBe("60");
    });
    const delta = screen.getByTestId("delta");
    expect(delta.textContent).toBe("-46 cycles vs baseline (-43%)");
    expect(delta.getAttribute("style")).toContain("var(--rd)");
    expect(temps).toEqual(["25", "35"]);
    server.events.removeAllListeners();
  });

  it("writes EOL to the shared draft (D1) and keeps the last result if a simulation fails", async () => {
    function Probe() {
      const d = useScenarioDraft();
      return (
        <output data-testid="probe">
          {String(d.params?.eol_pct)} {String(d.changed.eolPct)}
        </output>
      );
    }
    renderWithProviders(
      <>
        <Probe />
        <SimulatorPage />
      </>,
    );
    await results();
    // No recorded simulation exists for EOL 70, so this request fails (500).
    fireEvent.change(slider(/^End-of-life SOH/), { target: { value: "70" } });
    expect(screen.getByTestId("probe").textContent).toBe("70 true");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Showing the previous result.");
    expect(screen.getByTestId("cycles-to-eol").textContent).toBe("106");
  });

  it("Reset returns every slider to the API defaults", async () => {
    const { user } = renderApp("/simulator");
    await results();
    fireEvent.change(slider(/^Temperature/), { target: { value: "35" } });
    await waitFor(() => {
      expect(screen.getByTestId("cycles-to-eol").textContent).toBe("60");
    });
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(slider(/^Temperature/).value).toBe("25");
    await waitFor(() => {
      expect(screen.getByTestId("cycles-to-eol").textContent).toBe("106");
    });
  });
});

describe("saved scenarios", () => {
  it("saves, overlays, duplicates and deletes", async () => {
    const { user } = renderApp("/simulator");
    await results();
    await user.click(screen.getByRole("button", { name: "Save scenario" }));
    const item = await screen.findByTestId("saved-scenario");
    expect(item.textContent).toContain("Scenario 1");
    expect(item.textContent).toContain("25°C · 1C · 80%");
    expect(
      within(item).getByText("Scenario 1").getAttribute("style"),
    ).toContain("var(--am)");
    await waitFor(() => {
      expect(seriesNames()).toEqual(["Baseline", "Current", "Scenario 1"]);
    });
    await user.click(
      screen.getByRole("button", { name: "Duplicate Scenario 1" }),
    );
    await waitFor(() => {
      expect(screen.getAllByTestId("saved-scenario")).toHaveLength(2);
    });
    expect(storedScenarios().map((s) => s.name)).toEqual([
      "Scenario 1",
      "Scenario 1 copy",
    ]);
    await user.click(screen.getByRole("button", { name: "Delete Scenario 1" }));
    await waitFor(() => {
      expect(storedScenarios().map((s) => s.name)).toEqual(["Scenario 1 copy"]);
    });
    expect((await screen.findByTestId("saved-scenario")).textContent).toContain(
      "Scenario 1 copy",
    );
  });

  it("stops at four scenarios (D3) for Save and Duplicate", async () => {
    resetScenarioStore(saved(4));
    const { user } = renderApp("/simulator");
    await results();
    expect(await screen.findAllByTestId("saved-scenario")).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "Save scenario" }));
    expect(
      await screen.findByText("Delete a scenario first (max 4)."),
    ).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Duplicate Scenario 2" }),
    );
    expect(storedScenarios()).toHaveLength(4);
    await waitFor(() => {
      expect(seriesNames()).toHaveLength(6);
    });
  });

  it("draws at most four overlays when the API holds more", async () => {
    resetScenarioStore(saved(5));
    renderApp("/simulator");
    await results();
    expect(await screen.findAllByTestId("saved-scenario")).toHaveLength(5);
    await waitFor(() => {
      expect(seriesNames()).toEqual([
        "Baseline",
        "Current",
        "Scenario 1",
        "Scenario 2",
        "Scenario 3",
        "Scenario 4",
      ]);
    });
  });

  it("renames in an accessible dialog limited to 30 characters (U2)", async () => {
    resetScenarioStore(saved(1));
    const { user } = renderApp("/simulator");
    await results();
    await user.click(
      await screen.findByRole("button", { name: "Rename Scenario 1" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Rename scenario" });
    const input = within(dialog).getByRole<HTMLInputElement>("textbox", {
      name: "Scenario name",
    });
    expect(input.value).toBe("Scenario 1");
    expect(input.maxLength).toBe(30);
    await user.clear(input);
    expect(
      within(dialog).getByRole<HTMLButtonElement>("button", { name: "Save" })
        .disabled,
    ).toBe(true);
    await user.type(input, "   Cold weather, gentle charging profile");
    expect(input.value).toHaveLength(30);
    expect(within(dialog).getByText("30/30 characters")).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(storedScenarios()[0]?.name).toBe("Cold weather, gentle chargi");
    });
    expect((await screen.findByTestId("saved-scenario")).textContent).toContain(
      "Cold weather, gentle chargi",
    );
  });

  it("cancels a rename without changing anything", async () => {
    resetScenarioStore(saved(1));
    const { user } = renderApp("/simulator");
    await results();
    await user.click(
      await screen.findByRole("button", { name: "Rename Scenario 1" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Rename scenario" });
    await user.type(within(dialog).getByRole("textbox"), " edited");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(storedScenarios()[0]?.name).toBe("Scenario 1");
    await user.click(screen.getByRole("button", { name: "Rename Scenario 1" }));
    expect(
      within(
        screen.getByRole("dialog", { name: "Rename scenario" }),
      ).getByRole<HTMLInputElement>("textbox").value,
    ).toBe("Scenario 1");
  });

  it("reports a failed save and keeps the list", async () => {
    server.use(
      http.post("*/api/v1/batteries/:id/scenarios", () =>
        apiError(503, "database_unavailable", "The database is not configured"),
      ),
    );
    const { user } = renderApp("/simulator");
    await results();
    await user.click(
      await screen.findByRole("button", { name: "Save scenario" }),
    );
    expect(
      await screen.findByText(
        "Could not save the scenario: The database is not configured",
      ),
    ).toBeTruthy();
    expect(screen.queryAllByTestId("saved-scenario")).toHaveLength(0);
  });

  it("disables saving when the scenario list cannot load, but still simulates", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/scenarios", () =>
        apiError(503, "database_unavailable", "The database is not configured"),
      ),
    );
    renderApp("/simulator");
    await results();
    expect(
      await screen.findByText(/Saving scenarios needs the database/),
    ).toBeTruthy();
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Save scenario" })
        .disabled,
    ).toBe(true);
    expect(screen.getByTestId("cycles-to-eol").textContent).toBe("106");
  });

  it("notes saved scenarios that could not be simulated", async () => {
    resetScenarioStore([
      {
        ...fixtures.scenario,
        params: { ...fixtures.scenario.params, temp_c: 44 },
      },
    ]);
    renderApp("/simulator");
    await results();
    expect(
      await screen.findByText(
        "Some saved scenarios could not be simulated and are not drawn.",
      ),
    ).toBeTruthy();
    expect(seriesNames()).toEqual(["Baseline", "Current"]);
  });

  it("shows the configuration error with a retry", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/simulator", () =>
        apiError(500, "internal_error", "Simulator configuration failed"),
      ),
    );
    renderApp("/simulator");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Simulator configuration failed");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
