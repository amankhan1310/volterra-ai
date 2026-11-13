import type { components } from "./schema";

/** Response and request models generated from `backend/openapi.json` (see `npm run api:types`). */
export type Schemas = components["schemas"];

export type Health = Schemas["HealthResponse"];
export type Battery = Schemas["BatteryOut"];
export type Anomalies = Schemas["AnomaliesResponse"];
export type SimulatorConfig = Schemas["SimulatorConfigResponse"];
export type ScenarioParams = Schemas["ScenarioParamsModel"];
export type ApiErrorBody = Schemas["ErrorResponse"];

/** Every analytical value carries one of these (plan §6.3). */
export type Provenance = Schemas["Quantity"]["provenance"];
