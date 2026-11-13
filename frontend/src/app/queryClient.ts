import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";

/**
 * v1 analytics are deterministic for a given dataset, so results never go stale on their own;
 * "Run analysis" refreshes them explicitly. Only unreachable/5xx failures are retried, once.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity,
        gcTime: 30 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) =>
          failureCount < 1 &&
          error instanceof ApiError &&
          (error.status === 0 || error.status >= 500),
      },
    },
  });
}
