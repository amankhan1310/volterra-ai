import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { Anomalies, Battery, Health, SimulatorConfig } from "../api/types";
import anomaliesJson from "./fixtures/anomalies.json";
import batteriesJson from "./fixtures/batteries.json";
import healthJson from "./fixtures/health.json";
import simulatorJson from "./fixtures/simulator.json";

/** Recorded API responses (see fixtures/README.md), typed against the generated contract. */
export const fixtures = {
  health: healthJson as Health,
  batteries: batteriesJson as { items: Battery[] },
  battery: batteriesJson.items[0] as Battery,
  anomalies: anomaliesJson as Anomalies,
  simulator: simulatorJson as SimulatorConfig,
};

export const handlers = [
  http.get("*/api/v1/health", () => HttpResponse.json(fixtures.health)),
  http.get("*/api/v1/batteries", () => HttpResponse.json(fixtures.batteries)),
  http.get("*/api/v1/batteries/:id/anomalies", () =>
    HttpResponse.json(fixtures.anomalies),
  ),
  http.get("*/api/v1/batteries/:id/simulator", () =>
    HttpResponse.json(fixtures.simulator),
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
