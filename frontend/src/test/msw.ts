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
  Scenario,
  ScenarioParams,
  Simulation,
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
import scenarioJson from "./fixtures/scenario.json";
import simulateDefaultJson from "./fixtures/simulate-default.json";
import simulateT35Json from "./fixtures/simulate-t35.json";
import simulatorJson from "./fixtures/simulator.json";
import summaryEol70Json from "./fixtures/summary-eol-70.json";
import summaryJson from "./fixtures/summary.json";
import twin0Json from "./fixtures/twin-0.json";
import twin160Json from "./fixtures/twin-160.json";
import twin170Json from "./fixtures/twin-170.json";
import twin319Json from "./fixtures/twin-319.json";

// The recorded JSON already matches `Scenario`; the annotation keeps it checked against the contract.
const scenarioFixture: Scenario = scenarioJson;

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
  /** `POST /simulate` for the defaults and for temperature 35 °C. */
  simulateDefault: simulateDefaultJson as Simulation,
  simulateT35: simulateT35Json as Simulation,
  /** A real `ScenarioOut` (ids and timestamps normalised). */
  scenario: scenarioFixture,
};

const paramsKey = (p: ScenarioParams) =>
  [p.temp_c, p.c_rate, p.dod_pct, p.horizon_cycles, p.start_soh_pct, p.eol_pct]
    .map(Number)
    .join("|");

const SIMULATIONS = new Map(
  [fixtures.simulateDefault, fixtures.simulateT35].map((s) => [
    paramsKey(s.params),
    s,
  ]),
);

/**
 * Saved scenarios for the current test: real record shape, kept in memory and emptied after every
 * test (see setup.ts). Names follow the API's rules (trimmed, 1–60 characters).
 */
let scenarioStore: Scenario[] = [];
let nextScenario = 1;
export function resetScenarioStore(initial: Scenario[] = []): void {
  scenarioStore = initial.map((s) => ({ ...s }));
  nextScenario = initial.length + 1;
}
export const storedScenarios = (): readonly Scenario[] => scenarioStore;

function nameError(name: unknown) {
  const trimmed = typeof name === "string" ? name.trim() : "";
  return trimmed.length < 1 || trimmed.length > 60
    ? HttpResponse.json(
        {
          error: {
            code: "validation_error",
            message: "Request validation failed",
            details: null,
          },
        },
        { status: 422 },
      )
    : null;
}

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
  http.post("*/api/v1/batteries/:id/simulate", async ({ request }) => {
    const body = (await request.json()) as { params: ScenarioParams };
    const sim = SIMULATIONS.get(paramsKey(body.params));
    return sim
      ? HttpResponse.json(sim)
      : HttpResponse.json(
          {
            error: {
              code: "test_fixture_missing",
              message: `No fixture for simulate ${paramsKey(body.params)}`,
              details: null,
            },
          },
          { status: 500 },
        );
  }),
  http.get("*/api/v1/batteries/:id/scenarios", () =>
    HttpResponse.json({ items: scenarioStore }),
  ),
  http.post("*/api/v1/batteries/:id/scenarios", async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      params: ScenarioParams;
    };
    const invalid = nameError(body.name);
    if (invalid) return invalid;
    const n = nextScenario++;
    const created: Scenario = {
      ...fixtures.scenario,
      id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
      name: body.name.trim(),
      params: body.params,
    };
    scenarioStore = [...scenarioStore, created];
    return HttpResponse.json(created, { status: 201 });
  }),
  http.patch("*/api/v1/scenarios/:sid", async ({ request, params }) => {
    const body = (await request.json()) as { name?: string };
    const invalid = nameError(body.name);
    if (invalid) return invalid;
    const found = scenarioStore.find((s) => s.id === params["sid"]);
    if (!found) return apiError(404, "not_found", "Scenario not found");
    const updated = { ...found, name: (body.name ?? "").trim() };
    scenarioStore = scenarioStore.map((s) => (s.id === found.id ? updated : s));
    return HttpResponse.json(updated);
  }),
  http.delete("*/api/v1/scenarios/:sid", ({ params }) => {
    const before = scenarioStore.length;
    scenarioStore = scenarioStore.filter((s) => s.id !== params["sid"]);
    return scenarioStore.length === before
      ? apiError(404, "not_found", "Scenario not found")
      : new HttpResponse(null, { status: 204 });
  }),
];

export const server = setupServer(...handlers);

/** The backend's error envelope. */
export function apiError(status: number, code: string, message: string) {
  return HttpResponse.json(
    { error: { code, message, details: null } },
    { status },
  );
}
