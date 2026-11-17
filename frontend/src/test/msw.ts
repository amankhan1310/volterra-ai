import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type {
  Advisor,
  Anomalies,
  Backtest,
  Battery,
  Capacity,
  Cycles,
  CycleSamples,
  Forecast,
  Health,
  Insights,
  Models,
  RulPredictions,
  Scenario,
  ScenarioParams,
  Simulation,
  SimulatorConfig,
  SimulatorEvidence,
  Summary,
  Twin,
} from "../api/types";
import advisorEol70Soh90Json from "./fixtures/advisor-eol70-soh90.json";
import advisorEol90Soh85Json from "./fixtures/advisor-eol90-soh85.json";
import advisorJson from "./fixtures/advisor.json";
import anomaliesJson from "./fixtures/anomalies.json";
import backtestJson from "./fixtures/backtest.json";
import batteriesJson from "./fixtures/batteries.json";
import cyclesCalceJson from "./fixtures/cycles-calce.json";
import capacityCalceJson from "./fixtures/capacity-calce.json";
import capacityNasaJson from "./fixtures/capacity-nasa.json";
import capacitySyntheticJson from "./fixtures/capacity-synthetic.json";
import cyclesNasaJson from "./fixtures/cycles-nasa.json";
import cyclesJson from "./fixtures/cycles.json";
import errorInsufficientJson from "./fixtures/error-insufficient-data.json";
import errorMissingJson from "./fixtures/error-missing-measurement.json";
import errorNoPredictionsJson from "./fixtures/error-no-predictions.json";
import errorNoSamplesJson from "./fixtures/error-no-samples.json";
import forecastEol70Json from "./fixtures/forecast-eol-70.json";
import forecastJson from "./fixtures/forecast.json";
import healthJson from "./fixtures/health.json";
import insightsJson from "./fixtures/insights.json";
import modelsJson from "./fixtures/models.json";
import rulCalceJson from "./fixtures/rul-calce.json";
import rulNasaJson from "./fixtures/rul-nasa.json";
import samplesCalce7Json from "./fixtures/samples-calce-7.json";
import samplesNasa0Json from "./fixtures/samples-nasa-0.json";
import scenarioJson from "./fixtures/scenario.json";
import simulateDefaultJson from "./fixtures/simulate-default.json";
import simulateT35Json from "./fixtures/simulate-t35.json";
import simulatorEvidenceJson from "./fixtures/simulator-evidence.json";
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
  /** Charging Advisor at the defaults, at EOL 70% from 90% SOH and at EOL 90% from 85% SOH. */
  advisor: advisorJson as Advisor,
  advisorEol70Soh90: advisorEol70Soh90Json as Advisor,
  advisorEol90Soh85: advisorEol90Soh85Json as Advisor,
  /** Generated real-style batteries (see record-fixtures.mjs): CALCE-like and NASA-like. */
  calce: batteriesJson.items.find((b) => b.dataset === "calce-test") as Battery,
  nasa: batteriesJson.items.find((b) => b.dataset === "nasa-test") as Battery,
  cyclesCalce: cyclesCalceJson as unknown as Cycles,
  cyclesNasa: cyclesNasaJson as Cycles,
  /** Capacity degradation and SOH from the measured capacity. */
  capacityCalce: capacityCalceJson as Capacity,
  capacityNasa: capacityNasaJson as Capacity,
  capacitySynthetic: capacitySyntheticJson as Capacity,
  samplesNasa0: samplesNasa0Json as CycleSamples,
  samplesCalce7: samplesCalce7Json as unknown as CycleSamples,
  /** Phase 7: the generated model run (made-up values) and its stored RUL predictions. */
  models: modelsJson as Models,
  rulCalce: rulCalceJson as RulPredictions,
  rulNasa: rulNasaJson as RulPredictions,
  /** Phase 8: evidence behind the simulator's assumptions. */
  simulatorEvidence: simulatorEvidenceJson as SimulatorEvidence,
};

interface RecordedError {
  status: number;
  body: unknown;
}
/** What the API answers for each real-style battery's analytics (recorded 422s). */
const REAL_ANALYTICS_ERROR: Record<string, RecordedError> = {
  [fixtures.calce.id]: errorMissingJson,
  [fixtures.nasa.id]: errorInsufficientJson,
};
const CYCLES_BY_ID: Record<string, Cycles> = {
  [fixtures.battery.id]: fixtures.cycles,
  [fixtures.calce.id]: fixtures.cyclesCalce,
  [fixtures.nasa.id]: fixtures.cyclesNasa,
};
const SAMPLES: Record<string, CycleSamples> = {
  [`${fixtures.nasa.id}|0`]: fixtures.samplesNasa0,
  [`${fixtures.calce.id}|7`]: fixtures.samplesCalce7,
};
const recorded = (e: RecordedError) =>
  HttpResponse.json(e.body as object, { status: e.status });

const ADVISOR: Record<string, Advisor> = {
  "80|86.1": fixtures.advisor,
  "70|90": fixtures.advisorEol70Soh90,
  "90|85": fixtures.advisorEol90Soh85,
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
  // Analytics of a real-style battery answer with the recorded 422 (gated pages must never ask);
  // its cycles are served below and its twin was not recorded.
  http.get("*/api/v1/batteries/:id/:endpoint", ({ params }) => {
    const error = REAL_ANALYTICS_ERROR[String(params["id"])];
    const own = ["cycles", "rul-predictions", "capacity"].includes(
      String(params["endpoint"]),
    );
    if (!error || own) return undefined;
    return params["endpoint"] === "twin"
      ? apiError(500, "test_fixture_missing", "No twin fixture")
      : recorded(error);
  }),
  http.get("*/api/v1/health", () => HttpResponse.json(fixtures.health)),
  http.get("*/api/v1/models", () => HttpResponse.json(fixtures.models)),
  http.get("*/api/v1/simulator/evidence", () =>
    HttpResponse.json(fixtures.simulatorEvidence),
  ),
  http.get("*/api/v1/batteries/:id/rul-predictions", ({ params }) => {
    const id = String(params["id"]);
    if (id === fixtures.calce.id) return HttpResponse.json(fixtures.rulCalce);
    if (id === fixtures.nasa.id) return HttpResponse.json(fixtures.rulNasa);
    return recorded(errorNoPredictionsJson);
  }),
  http.get("*/api/v1/batteries/:id/capacity", ({ params }) => {
    const id = String(params["id"]);
    if (id === fixtures.calce.id)
      return HttpResponse.json(fixtures.capacityCalce);
    if (id === fixtures.nasa.id)
      return HttpResponse.json(fixtures.capacityNasa);
    return HttpResponse.json(fixtures.capacitySynthetic);
  }),
  http.get("*/api/v1/batteries", () => HttpResponse.json(fixtures.batteries)),
  http.get("*/api/v1/batteries/:id/anomalies", () =>
    HttpResponse.json(fixtures.anomalies),
  ),
  http.get("*/api/v1/batteries/:id/simulator", () =>
    HttpResponse.json(fixtures.simulator),
  ),
  http.get("*/api/v1/batteries/:id/cycles", ({ params }) => {
    const body = CYCLES_BY_ID[String(params["id"])];
    return body
      ? HttpResponse.json(body)
      : apiError(404, "battery_not_found", "Battery not found");
  }),
  http.get("*/api/v1/batteries/:id/cycles/:cycle/samples", ({ params }) => {
    const id = String(params["id"]);
    if (id === fixtures.battery.id) return recorded(errorNoSamplesJson);
    const body = SAMPLES[`${id}|${String(params["cycle"])}`];
    return body
      ? HttpResponse.json(body)
      : apiError(500, "test_fixture_missing", "No samples fixture");
  }),
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
  http.get("*/api/v1/batteries/:id/advisor", ({ request }) => {
    const q = new URL(request.url).searchParams;
    const key = `${q.get("eol_pct") ?? ""}|${q.get("start_soh_pct") ?? ""}`;
    const body = ADVISOR[key];
    return body
      ? HttpResponse.json(body)
      : apiError(500, "test_fixture_missing", `No fixture for advisor ${key}`);
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
