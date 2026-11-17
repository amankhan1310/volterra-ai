import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { ModelTask } from "../../api/types";
import { fixtures, server } from "../../test/msw";
import { renderApp } from "../../test/render";
import { MIN_STABLE_TEST_BATTERIES, taskLabel, taskOrder } from "./ModelsPage";

const text = (el: Element) => el.textContent;

describe("Models page (Phase 7)", () => {
  it("shows the run's provenance, experimental status and how to read CV vs test", async () => {
    renderApp("/models");
    expect(text(await screen.findByTestId("run-id"))).toBe(
      fixtures.models.run?.run_id,
    );
    expect(screen.getByText("Experimental")).toBeTruthy();
    expect(text(screen.getByTestId("how-to-read"))).toContain(
      "Held-out test: batteries never used for training, calibration or model choice",
    );
    expect(screen.getByText(fixtures.models.note)).toBeTruthy();
    expect(fixtures.models.note).toContain("Not production-validated");
    expect(document.body.textContent).not.toMatch(
      /\b(is|are) production[- ]validated|validated for production/i,
    );
  });

  it("lists every candidate per dataset with CV, held-out test and calibration columns", async () => {
    renderApp("/models");
    const rul = await screen.findByTestId("task-rul");
    const headers = within(rul)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "Model",
      "Cross-validation MAE (cycles)",
      "Held-out test MAE",
      "Test RMSE",
      "Test R²",
      "Test coverage (90% nominal)",
      "Test interval width",
      "Calibration set",
    ]);
    const rows = within(rul).getAllByRole("row");
    const lgbm = rows.find((r) => r.textContent.startsWith("lightgbm"));
    expect(lgbm?.textContent).toContain("(selected)");
    const baseline = rows.find((r) => r.textContent.startsWith("linear_trend"));
    expect(baseline?.textContent).toContain("baseline");
    expect(text(rul)).toContain("calce-test: 5 train / 3 calibration / 1 test");
    expect(text(within(rul).getByTestId("small-test-warning"))).toContain(
      `Fewer than ${String(MIN_STABLE_TEST_BATTERIES)} held-out test batteries`,
    );
  });

  it("orders tasks: RUL, forecasts by horizon, SOH estimation, stress test", () => {
    const tasks = [
      "soh_x",
      "rul_cross_dataset",
      "forecast_h200",
      "rul",
      "forecast_h50",
    ];
    expect(tasks.sort((a, b) => taskOrder(a) - taskOrder(b))).toEqual([
      "rul",
      "forecast_h50",
      "forecast_h200",
      "soh_x",
      "rul_cross_dataset",
    ]);
  });

  it("names tasks with their error unit", () => {
    const task = (t: Partial<ModelTask>) =>
      ({ ...fixtures.models.tasks[0], ...t }) as ModelTask;
    expect(taskLabel(task({ task: "rul" }))).toEqual({
      title: "Remaining useful life",
      unit: "cycles",
    });
    expect(
      taskLabel(
        task({ task: "forecast_h50", kind: "forecast", horizon_cycles: 50 }),
      ).title,
    ).toBe("SOH forecast, 50 cycles ahead");
    expect(
      taskLabel(task({ task: "soh_severson-2019", kind: "soh" })).title,
    ).toBe("SOH estimation from measured signals (severson-2019)");
    expect(taskLabel(task({ task: "rul_cross_dataset" })).title).toContain(
      "trained on Severson only",
    );
  });

  it("explains how to import a run when none exists", async () => {
    server.use(
      http.get("*/api/v1/models", () =>
        HttpResponse.json({ ...fixtures.models, run: null, tasks: [] }),
      ),
    );
    renderApp("/models");
    expect(await screen.findByText("No model run imported")).toBeTruthy();
    expect(
      screen.getByText("python -m app.db.import_models <run-dir>"),
    ).toBeTruthy();
    // A settled page (a synthetic-only deployment has no run), not a loading or error state.
    expect(screen.getByTestId("page-content").textContent).toContain(
      "No model run imported",
    );
  });
});

describe("RUL panel on Battery Data", () => {
  it("shows the interval, provenance, split and the experimental warning", async () => {
    renderApp("/battery-data?battery=calce-test:CS2_T");
    const panel = await screen.findByTestId("rul-panel");
    expect(text(await within(panel).findByTestId("rul-warning"))).toContain(
      "not production-validated",
    );
    const before = fixtures.rulCalce.points.filter((p) => !p.past_eol);
    const last = before.at(-1);
    expect(text(within(panel).getByTestId("rul-past-eol"))).toBe(
      `This battery reached its end of life at cycle ${String(fixtures.rulCalce.eol_cycle)} (from its measured data): no remaining life is predicted after that.`,
    );
    expect(text(within(panel).getByTestId("rul-latest"))).toBe(
      `Last prediction before EOL, at cycle ${String(last?.cycle)}: predicted remaining life ${String(last?.rul.point)} cycles, 90% interval ${String(last?.rul.lower)}–${String(last?.rul.upper)} cycles (split-conformal, calibrated on held-out batteries of this dataset); actual ${String(last?.actual_rul?.value)} cycles.`,
    );
    expect(text(within(panel).getByTestId("rul-split"))).toContain(
      "Held-out test battery",
    );
    expect(
      within(panel)
        .getByTestId("rul-split")
        .querySelector('[data-provenance="predicted"]'),
    ).not.toBeNull();
    expect(within(panel).getByRole("link", { name: "Models" })).toBeTruthy();
  });

  it("marks training batteries as in-sample and censored batteries as unknown", async () => {
    renderApp("/battery-data?battery=nasa-test:B0005");
    const split = await screen.findByTestId("rul-split");
    expect(text(split)).toContain("in-sample");
    expect(text(split)).toContain("never reaches EOL");
  });

  it("makes no prediction for the synthetic battery and never asks for one", async () => {
    renderApp("/battery-data");
    expect(text(await screen.findByTestId("rul-none"))).toContain(
      "no predictions for the synthetic reference battery",
    );
  });

  it("says so when the latest run has no prediction for a real battery", async () => {
    server.use(
      http.get("*/api/v1/batteries/:id/rul-predictions", () =>
        HttpResponse.json(
          {
            error: {
              code: "predictions_not_found",
              message: "No model predictions",
              details: null,
            },
          },
          { status: 404 },
        ),
      ),
    );
    renderApp("/battery-data?battery=calce-test:CS2_T");
    expect(text(await screen.findByTestId("rul-none"))).toContain(
      "No model prediction for CS2_T",
    );
  });
});
