import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, request } from "./client";
import type { Battery } from "./types";

/** Query keys: one factory so invalidation and tests agree on the shapes. */
export const queryKeys = {
  health: ["health"] as const,
  batteries: ["batteries"] as const,
  anomalies: (batteryId: string) =>
    ["batteries", batteryId, "anomalies"] as const,
  simulatorConfig: (batteryId: string) =>
    ["batteries", batteryId, "simulator"] as const,
  cycles: (batteryId: string) => ["batteries", batteryId, "cycles"] as const,
  summary: (batteryId: string, eolPct: number | undefined) =>
    ["batteries", batteryId, "summary", { eolPct }] as const,
  forecast: (batteryId: string, eolPct: number | undefined) =>
    ["batteries", batteryId, "forecast", { eolPct }] as const,
  backtest: (batteryId: string) =>
    ["batteries", batteryId, "backtest"] as const,
  insights: (batteryId: string) =>
    ["batteries", batteryId, "insights"] as const,
};

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
    placeholderData: keepPreviousData,
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
    placeholderData: keepPreviousData,
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

/**
 * The battery every page analyses. Phase 4 has a single seeded battery; the multi-battery
 * selector arrives with real data in Phase 6. `battery` is `null` when the database has none.
 */
export function useDefaultBattery() {
  const query = useBatteries();
  const battery: Battery | null | undefined = query.data
    ? (query.data.items[0] ?? null)
    : undefined;
  return { ...query, battery };
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
