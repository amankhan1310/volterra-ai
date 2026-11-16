import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api, request } from "./client";
import type { Battery, Scenario, ScenarioParams } from "./types";

/** Query keys: one factory so invalidation and tests agree on the shapes. */
export const queryKeys = {
  health: ["health"] as const,
  batteries: ["batteries"] as const,
  anomalies: (batteryId: string) =>
    ["batteries", batteryId, "anomalies"] as const,
  simulatorConfig: (batteryId: string) =>
    ["batteries", batteryId, "simulator"] as const,
  cycles: (batteryId: string) => ["batteries", batteryId, "cycles"] as const,
  samples: (batteryId: string, cycle: number | undefined) =>
    ["batteries", batteryId, "samples", { cycle }] as const,
  summary: (batteryId: string, eolPct: number | undefined) =>
    ["batteries", batteryId, "summary", { eolPct }] as const,
  forecast: (batteryId: string, eolPct: number | undefined) =>
    ["batteries", batteryId, "forecast", { eolPct }] as const,
  backtest: (batteryId: string) =>
    ["batteries", batteryId, "backtest"] as const,
  insights: (batteryId: string) =>
    ["batteries", batteryId, "insights"] as const,
  twin: (batteryId: string, cycle: number | undefined) =>
    ["batteries", batteryId, "twin", { cycle }] as const,
  simulate: (batteryId: string, params: ScenarioParams | null) =>
    ["batteries", batteryId, "simulate", params] as const,
  scenarios: (batteryId: string) =>
    ["batteries", batteryId, "scenarios"] as const,
  advisor: (
    batteryId: string,
    eolPct: number | undefined,
    startSohPct: number | undefined,
  ) => ["batteries", batteryId, "advisor", { eolPct, startSohPct }] as const,
};

/**
 * Keeps the previous result on screen while new parameters load (no flicker), but only for the
 * same battery: after a battery switch nothing from the previous battery is ever shown.
 */
function sameBattery(batteryId: string | undefined) {
  return <T>(
    previous: T | undefined,
    query: { queryKey: readonly unknown[] } | undefined,
  ): T | undefined =>
    query !== undefined && query.queryKey[1] === batteryId
      ? previous
      : undefined;
}

const batteryPath = (batteryId: string | undefined) => ({
  path: { battery_id: batteryId ?? "" },
});

export function useCycles(batteryId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.cycles(batteryId ?? ""),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/cycles", {
          params: batteryPath(batteryId),
        }),
      ),
    enabled: batteryId !== undefined,
  });
}

/**
 * `eolPct` comes from the shared simulator draft (D1). The query waits until it is known, so a
 * page never shows a result for the wrong threshold, and keeps the previous result on screen
 * while a new threshold loads.
 */
export function useSummary(
  batteryId: string | undefined,
  eolPct: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.summary(batteryId ?? "", eolPct),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/summary", {
          params: {
            ...batteryPath(batteryId),
            query: eolPct === undefined ? {} : { eol_pct: eolPct },
          },
        }),
      ),
    enabled: batteryId !== undefined && eolPct !== undefined,
    placeholderData: sameBattery(batteryId),
  });
}

export function useForecast(
  batteryId: string | undefined,
  eolPct: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.forecast(batteryId ?? "", eolPct),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/forecast", {
          params: {
            ...batteryPath(batteryId),
            query: eolPct === undefined ? {} : { eol_pct: eolPct },
          },
        }),
      ),
    enabled: batteryId !== undefined && eolPct !== undefined,
    placeholderData: sameBattery(batteryId),
  });
}

export function useBacktest(batteryId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.backtest(batteryId ?? ""),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/backtest", {
          params: batteryPath(batteryId),
        }),
      ),
    enabled: batteryId !== undefined,
  });
}

export function useInsights(batteryId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.insights(batteryId ?? ""),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/insights", {
          params: batteryPath(batteryId),
        }),
      ),
    enabled: batteryId !== undefined,
  });
}

/** How often the API/database status indicator re-checks `/health` (U8). */
export const HEALTH_POLL_MS = 15_000;

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => request(() => api.GET("/api/v1/health")),
    // Status must reflect reality: always re-check, never retry silently.
    staleTime: 0,
    retry: false,
    refetchInterval: HEALTH_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useBatteries() {
  return useQuery({
    queryKey: queryKeys.batteries,
    queryFn: () => request(() => api.GET("/api/v1/batteries")),
  });
}

/** URL parameter that selects the battery (decision D11): `?battery=<dataset>:<external_id>`. */
export const BATTERY_PARAM = "battery";

/** Stable, readable battery key for the URL (database ids change between imports). */
export function batteryKey(battery: Pick<Battery, "dataset" | "external_id">) {
  return `${battery.dataset}:${battery.external_id}`;
}

/**
 * The battery every page shows: the one named by `?battery=`, else the first listed (the API
 * lists the synthetic reference battery first). `battery` is `null` when the database has
 * none, or when the requested battery does not exist (`notFound`).
 */
export function useDefaultBattery() {
  const query = useBatteries();
  const [params] = useSearchParams();
  const requested = params.get(BATTERY_PARAM);
  const items = query.data?.items;
  let battery: Battery | null | undefined;
  if (items) {
    battery =
      requested === null
        ? (items[0] ?? null)
        : (items.find((b) => batteryKey(b) === requested) ?? null);
  }
  return {
    ...query,
    battery,
    requested,
    notFound: items !== undefined && requested !== null && battery === null,
  };
}

/** `?battery=…` of the current URL (or ""), so links keep the selected battery. */
export function useBatterySearch(): string {
  const [params] = useSearchParams();
  const key = params.get(BATTERY_PARAM);
  return key === null
    ? ""
    : `?${new URLSearchParams({ [BATTERY_PARAM]: key }).toString()}`;
}

/** The selected battery's id, only when the analytics can run for it (otherwise the API 422s). */
export function useAnalysisBatteryId(): string | undefined {
  const { battery } = useDefaultBattery();
  return battery?.analysis.available ? battery.id : undefined;
}

/** Measured samples of one cycle (real datasets only; the synthetic data has none). */
export function useCycleSamples(
  batteryId: string | undefined,
  cycle: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.samples(batteryId ?? "", cycle),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/cycles/{cycle}/samples", {
          params: {
            path: { battery_id: batteryId ?? "", cycle: cycle ?? 0 },
            query: { max_points: 1500 },
          },
        }),
      ),
    enabled: batteryId !== undefined && cycle !== undefined,
    placeholderData: sameBattery(batteryId),
  });
}

export function useAnomalies(batteryId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.anomalies(batteryId ?? ""),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/anomalies", {
          params: { path: { battery_id: batteryId ?? "" } },
        }),
      ),
    enabled: batteryId !== undefined,
  });
}

export function useSimulatorConfig(batteryId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.simulatorConfig(batteryId ?? ""),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/simulator", {
          params: { path: { battery_id: batteryId ?? "" } },
        }),
      ),
    enabled: batteryId !== undefined,
  });
}

/**
 * Pack state at one cycle. Results are cached per cycle; while the next cycle loads, the previous
 * one stays on screen so dragging the slider never flickers.
 */
export function useTwin(
  batteryId: string | undefined,
  cycle: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.twin(batteryId ?? "", cycle),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/twin", {
          params: {
            ...batteryPath(batteryId),
            query: cycle === undefined ? {} : { cycle },
          },
        }),
      ),
    enabled: batteryId !== undefined && cycle !== undefined,
    placeholderData: sameBattery(batteryId),
  });
}

const simulateQuery = (batteryId: string, params: ScenarioParams | null) => ({
  queryKey: queryKeys.simulate(batteryId, params),
  queryFn: () =>
    request(() =>
      api.POST("/api/v1/batteries/{battery_id}/simulate", {
        params: batteryPath(batteryId),
        body: {
          // `params` is non-null whenever the query is enabled.
          params: params ?? ({} as ScenarioParams),
          include_trajectories: true,
        },
      }),
    ),
  enabled: params !== null,
});

/**
 * `POST /simulate` for one parameter set. A pure computation, so it is cached by its parameters
 * like a GET; the previous result stays on screen while the next one loads.
 */
export function useSimulation(
  batteryId: string,
  params: ScenarioParams | null,
) {
  return useQuery({
    ...simulateQuery(batteryId, params),
    placeholderData: sameBattery(batteryId),
  });
}

/** One simulation per parameter set (the saved-scenario overlays). */
export function useSimulations(
  batteryId: string,
  paramSets: readonly ScenarioParams[],
) {
  return useQueries({
    queries: paramSets.map((p) => simulateQuery(batteryId, p)),
  });
}

export function useScenarios(batteryId: string) {
  return useQuery({
    queryKey: queryKeys.scenarios(batteryId),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/scenarios", {
          params: batteryPath(batteryId),
        }),
      ),
  });
}

/** Create, rename and delete saved scenarios; each refreshes the battery's scenario list. */
export function useScenarioMutations(batteryId: string) {
  const queryClient = useQueryClient();
  const onSuccess = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.scenarios(batteryId) });
  const create = useMutation({
    mutationFn: (body: { name: string; params: ScenarioParams }) =>
      request(() =>
        api.POST("/api/v1/batteries/{battery_id}/scenarios", {
          params: batteryPath(batteryId),
          body,
        }),
      ),
    onSuccess,
  });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      request(() =>
        api.PATCH("/api/v1/scenarios/{scenario_id}", {
          params: { path: { scenario_id: id } },
          body: { name },
        }),
      ),
    onSuccess,
  });
  const remove = useMutation({
    mutationFn: (scenario: Scenario) =>
      request(() =>
        api.DELETE("/api/v1/scenarios/{scenario_id}", {
          params: { path: { scenario_id: scenario.id } },
        }),
      ),
    onSuccess,
  });
  return { create, rename, remove };
}

/**
 * Charging Advisor rows for the shared EOL threshold and initial SOH (D1). Waits until both are
 * known; the previous rows stay on screen while new parameters load.
 */
export function useAdvisor(
  batteryId: string,
  eolPct: number | undefined,
  startSohPct: number | undefined,
) {
  return useQuery({
    queryKey: queryKeys.advisor(batteryId, eolPct, startSohPct),
    queryFn: () =>
      request(() =>
        api.GET("/api/v1/batteries/{battery_id}/advisor", {
          params: {
            ...batteryPath(batteryId),
            query:
              eolPct === undefined || startSohPct === undefined
                ? {}
                : { eol_pct: eolPct, start_soh_pct: startSohPct },
          },
        }),
      ),
    enabled: eolPct !== undefined && startSohPct !== undefined,
    placeholderData: sameBattery(batteryId),
  });
}
