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
export type Capacity = Schemas["CapacityDegradationResponse"];
export type Cycle = Schemas["CycleOut"];
export type CycleSamples = Schemas["CycleSamplesResponse"];
export type AnomalyEvent = Schemas["AnomalyEventOut"];
export type HealthLevel = Summary["health_level"];
export type InsightKind = Schemas["InsightOut"]["kind"];
export type Twin = Schemas["TwinResponse"];
export type TemperatureBand = Twin["temperature_band"];
export type Simulation = Schemas["SimulateResponse"];
export type Scenario = Schemas["ScenarioOut"];
export type Slider = Schemas["SliderOut"];
export type Advisor = Schemas["AdvisorResponse"];
export type AdvisorRow = Schemas["AdvisorRowOut"];
export type Models = Schemas["ModelsResponse"];
export type ModelTask = Schemas["ModelTaskOut"];
export type ModelCandidate = Schemas["CandidateEvaluation"];
export type MetricSet = Schemas["MetricSet"];
export type RulPredictions = Schemas["RulPredictionsResponse"];
export type SimulatorEvidence = Schemas["SimulatorEvidenceResponse"];
