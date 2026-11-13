import { useQuery } from "@tanstack/react-query";
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
};

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
