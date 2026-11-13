import type { UseQueryResult } from "@tanstack/react-query";
import { describeError } from "../../api/errors";
import { ErrorState, Skeleton } from "../ui/States";

/**
 * What a card shows while any of its queries has no data: the first error (with a Retry that
 * re-runs the failed queries), otherwise a loading skeleton. Each card loads independently.
 */
export function QueryFallback({
  queries,
  label,
  height,
}: {
  queries: readonly UseQueryResult[];
  /** What is loading, e.g. "Loading the degradation timeline". */
  label: string;
  height?: number;
}) {
  const failed = queries.filter((q) => q.isError);
  const first = failed[0];
  if (first) {
    const d = describeError(first.error);
    return (
      <ErrorState
        title={d.title}
        message={d.message}
        hint={d.hint}
        code={d.code}
        onRetry={() => {
          for (const q of failed) void q.refetch();
        }}
      />
    );
  }
  return height === undefined ? (
    <Skeleton label={label} />
  ) : (
    <Skeleton label={label} height={height} />
  );
}
