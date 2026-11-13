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
  Twin,
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
import twin0Json from "./fixtures/twin-0.json";
import twin160Json from "./fixtures/twin-160.json";
import twin170Json from "./fixtures/twin-170.json";
import twin319Json from "./fixtures/twin-319.json";

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
  /** Pack state per recorded cycle. */
  twin: {
    0: twin0Json as Twin,
    160: twin160Json as Twin,
    170: twin170Json as Twin,
    319: twin319Json as Twin,
  } as Record<number, Twin>,
};

/**
 * Serves only parameter values that were actually recorded; any other value is a test bug and
 * gets a 500, so no test can pass on a response the API never produced.
 */
function byParam<T>(
  param: string,
  fallback: string,
  recorded: Record<string, T>,
) {
  return ({ request }: { request: Request }) => {
    const value = new URL(request.url).searchParams.get(param) ?? fallback;
    const body = recorded[value];
    return body === undefined
      ? HttpResponse.json(
          {
            error: {
              code: "test_fixture_missing",
              message: `No fixture for ${param}=${value}`,
              details: null,
            },
          },
          { status: 500 },
        )
      : HttpResponse.json(body);
  };
}

const byEol = <T>(recorded: Record<string, T>) =>
  byParam("eol_pct", "80", recorded);

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
  http.get(
    "*/api/v1/batteries/:id/twin",
    byParam("cycle", "319", fixtures.twin),
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
