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
export type Summary = Schemas["SummaryResponse"];
export type Forecast = Schemas["ForecastResponse"];
export type Backtest = Schemas["BacktestResponse"];
export type Insights = Schemas["InsightsResponse"];
export type Cycles = Schemas["CyclesResponse"];
export type Cycle = Schemas["CycleOut"];
export type AnomalyEvent = Schemas["AnomalyEventOut"];
export type HealthLevel = Summary["health_level"];
export type InsightKind = Schemas["InsightOut"]["kind"];
