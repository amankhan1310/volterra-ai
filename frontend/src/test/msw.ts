import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type {
  Anomalies,
  Backtest,
  Battery,
  Cycles,
  Forecast,
  Health,
  Insights,
  SimulatorConfig,
  Summary,
} from "../api/types";
import anomaliesJson from "./fixtures/anomalies.json";
import backtestJson from "./fixtures/backtest.json";
import batteriesJson from "./fixtures/batteries.json";
import cyclesJson from "./fixtures/cycles.json";
import forecastEol70Json from "./fixtures/forecast-eol-70.json";
import forecastJson from "./fixtures/forecast.json";
import healthJson from "./fixtures/health.json";
import insightsJson from "./fixtures/insights.json";
import simulatorJson from "./fixtures/simulator.json";
import summaryEol70Json from "./fixtures/summary-eol-70.json";
import summaryJson from "./fixtures/summary.json";

/** Recorded API responses (see fixtures/README.md), typed against the generated contract. */
export const fixtures = {
  health: healthJson as Health,
  batteries: batteriesJson as { items: Battery[] },
  battery: batteriesJson.items[0] as Battery,
  anomalies: anomaliesJson as Anomalies,
  simulator: simulatorJson as SimulatorConfig,
  cycles: cyclesJson as Cycles,
  summary: summaryJson as Summary,
  summaryEol70: summaryEol70Json as Summary,
  forecast: forecastJson as Forecast,
  forecastEol70: forecastEol70Json as Forecast,
  backtest: backtestJson as Backtest,
  insights: insightsJson as Insights,
};

/**
 * Only thresholds that were actually recorded are served; any other `eol_pct` is a test bug and
 * gets a 500, so no test can pass on a response the API never produced.
 */
function byEol<T>(recorded: Record<string, T>) {
  return ({ request }: { request: Request }) => {
    const eol = new URL(request.url).searchParams.get("eol_pct") ?? "80";
    const body = recorded[eol];
    return body === undefined
      ? HttpResponse.json(
          {
            error: {
              code: "test_fixture_missing",
              message: `No fixture for eol_pct=${eol}`,
              details: null,
            },
          },
          { status: 500 },
        )
      : HttpResponse.json(body);
  };
}

export const handlers = [
  http.get("*/api/v1/health", () => HttpResponse.json(fixtures.health)),
  http.get("*/api/v1/batteries", () => HttpResponse.json(fixtures.batteries)),
  http.get("*/api/v1/batteries/:id/anomalies", () =>
    HttpResponse.json(fixtures.anomalies),
  ),
  http.get("*/api/v1/batteries/:id/simulator", () =>
    HttpResponse.json(fixtures.simulator),
  ),
  http.get("*/api/v1/batteries/:id/cycles", () =>
    HttpResponse.json(fixtures.cycles),
  ),
  http.get(
    "*/api/v1/batteries/:id/summary",
    byEol({ "80": fixtures.summary, "70": fixtures.summaryEol70 }),
  ),
  http.get(
    "*/api/v1/batteries/:id/forecast",
    byEol({ "80": fixtures.forecast, "70": fixtures.forecastEol70 }),
  ),
  http.get("*/api/v1/batteries/:id/backtest", () =>
    HttpResponse.json(fixtures.backtest),
  ),
  http.get("*/api/v1/batteries/:id/insights", () =>
    HttpResponse.json(fixtures.insights),
  ),
];

export const server = setupServer(...handlers);

/** The backend's error envelope. */
export function apiError(status: number, code: string, message: string) {
  return HttpResponse.json(
    { error: { code, message, details: null } },
    { status },
  );
}
