import { screen } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import type { Battery, Health } from "../../api/types";
import { apiError, fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";
import { dataSourceLabel } from "./Header";
import { reloadMessage } from "./RunAnalysisButton";
import { dataSourceText, serviceStatus } from "./StatusCard";

const measured: Battery = {
  ...fixtures.battery,
  is_synthetic: false,
  data_provenance: "measured",
  dataset_name: "NASA PCoE",
  nominal_capacity_ah: 2.3,
};

describe("serviceStatus", () => {
  const health = (status: Health["database"]["status"]): Health => ({
    ...fixtures.health,
    database: { status, latency_ms: null, error: null },
  });

  it("maps /health to the status dot", () => {
    expect(serviceStatus(undefined, true)).toEqual({
      status: "offline",
      text: "API unreachable",
    });
    expect(serviceStatus(undefined, false)).toEqual({
      status: "checking",
      text: "Checking API…",
    });
    expect(serviceStatus(health("ok"), false).status).toBe("online");
    expect(serviceStatus(health("not_configured"), false)).toEqual({
      status: "degraded",
      text: "API online · database not configured",
    });
    expect(serviceStatus(health("unavailable"), false).text).toBe(
      "API online · database unavailable",
    );
  });
});

describe("dataSourceText", () => {
  it("keeps the legacy wording for synthetic data", () => {
    expect(dataSourceText(fixtures.battery)).toEqual({
      title: "Simulation mode",
      detail: "Seeded dataset · no vehicle link",
    });
  });

  it("names measured data honestly", () => {
    expect(dataSourceText(measured)).toEqual({
      title: "Measured data",
      detail: "NASA PCoE · no vehicle link",
    });
    expect(dataSourceText(null).title).toBe("No data");
    expect(dataSourceText(undefined).title).toBe("Data source");
  });
});

describe("header data-source pill", () => {
  it("reproduces the legacy text from the battery record", () => {
    expect(dataSourceLabel(fixtures.battery)).toBe(
      "Simulated · 2.0 Ah cell profile",
    );
    expect(dataSourceLabel(measured)).toBe("Measured · 2.3 Ah cell profile");
  });

  it("describes measured data in its tooltip", async () => {
    server.use(
      http.get("*/api/v1/batteries", () =>
        Response.json({ items: [measured] }),
      ),
    );
    renderApp("/overview");
    const pill = await screen.findByText("Measured · 2.3 Ah cell profile");
    expect(pill.getAttribute("title")).toBe("Measured data from NASA PCoE");
  });
});

describe("Run analysis (D6)", () => {
  it("builds an honest message", () => {
    expect(reloadMessage("synthetic-v1", "v1")).toBe(
      "Analysis results reloaded from the API (synthetic-v1, algorithm v1). No model was retrained.",
    );
    expect(reloadMessage(undefined, undefined)).toBe(
      "Analysis results reloaded from the API. No model was retrained.",
    );
  });

  it("refetches and reports a reload, not a retrain", async () => {
    let batteryRequests = 0;
    server.use(
      http.get("*/api/v1/batteries", () => {
        batteryRequests += 1;
        return Response.json(fixtures.batteries);
      }),
    );
    const { user } = renderApp("/overview");
    await screen.findByTestId("page-placeholder");
    await screen.findByText("v1");
    const before = batteryRequests;
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(
      await screen.findByText(
        "Analysis results reloaded from the API (synthetic-v1, algorithm v1). No model was retrained.",
      ),
    ).toBeTruthy();
    expect(batteryRequests).toBeGreaterThan(before);
    expect(screen.getByRole("button", { name: "Run analysis" })).toBeTruthy();
  });

  it("reports a failed reload", async () => {
    const { user } = renderApp("/overview");
    await screen.findByTestId("page-placeholder");
    server.use(
      http.get("*/api/v1/batteries", () =>
        apiError(503, "database_unavailable", "The database is not configured"),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Run analysis" }));
    expect(
      await screen.findByText("Reload failed: The database is not configured"),
    ).toBeTruthy();
  });
});
