import type { ReactNode } from "react";
import { useDefaultBattery } from "../../api/hooks";
import { describeError } from "../../api/errors";
import type { Battery } from "../../api/types";
import { EmptyState, ErrorState, Skeleton } from "../ui/States";

/**
 * Renders page content only once the battery is known; otherwise the loading, error
 * (API unreachable / database unavailable) or empty (database not seeded) state.
 */
export function BatteryGate({
  children,
}: {
  children: (battery: Battery) => ReactNode;
}) {
  const { battery, error, isPending, refetch } = useDefaultBattery();

  if (isPending) return <Skeleton label="Loading battery data" height={160} />;

  if (error) {
    const d = describeError(error);
    return (
      <ErrorState
        title={d.title}
        message={d.message}
        hint={d.hint}
        code={d.code}
        onRetry={() => void refetch()}
      />
    );
  }

  if (!battery) {
    return (
      <EmptyState title="No battery data">
        <p>
          The database has no batteries yet, so there is nothing to analyse.
        </p>
        <p>
          Seed the synthetic dataset:{" "}
          <code>cd backend &amp;&amp; uv run python -m app.db.seed</code>
        </p>
      </EmptyState>
    );
  }

  return <>{children(battery)}</>;
}
