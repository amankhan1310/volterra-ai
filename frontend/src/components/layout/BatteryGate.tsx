import type { ReactNode } from "react";
import { Link } from "react-router";
import {
  BATTERY_PARAM,
  batteryKey,
  useBatteries,
  useDefaultBattery,
} from "../../api/hooks";
import { describeError } from "../../api/errors";
import type { Battery } from "../../api/types";
import { getPage } from "../../app/pages";
import { EmptyState, ErrorState, Skeleton } from "../ui/States";

/**
 * What a page needs from the battery: `analysis` = the v1/v2 analytics (enough cycles and every
 * measurement, decisions D3/D4); `measurements` = temperature and voltage on every cycle.
 */
export type BatteryNeed = "analysis" | "measurements";

const selectSearch = (battery: Battery) =>
  `?${new URLSearchParams({ [BATTERY_PARAM]: batteryKey(battery) }).toString()}`;

/** Explains why this page cannot run for the selected battery and where to go instead. */
export function LimitationState({
  battery,
  need,
}: {
  battery: Battery;
  need: BatteryNeed;
}) {
  const reference = useBatteries().data?.items.find((b) => b.is_synthetic);
  const message =
    need === "analysis"
      ? battery.analysis.message
      : `${String(battery.incomplete_cycle_count)} of ${String(battery.cycle_count)} cycles have no temperature or voltage measurement; this view needs both and never fills them in.`;
  return (
    <EmptyState
      title={
        need === "analysis"
          ? `Analytics are not available for ${battery.external_id}`
          : `This view is not available for ${battery.external_id}`
      }
    >
      <p data-testid="limitation-message">{message}</p>
      <p>
        Its measured data is shown on{" "}
        <Link
          to={{ pathname: getPage("data").path, search: selectSearch(battery) }}
        >
          Battery Data
        </Link>
        {reference ? (
          <>
            ; the full analytics run on the{" "}
            <Link to={{ search: selectSearch(reference) }}>
              synthetic reference battery
            </Link>
          </>
        ) : null}
        .
      </p>
    </EmptyState>
  );
}

/**
 * Renders page content only once the battery is known; otherwise the loading, error
 * (API unreachable / database unavailable), unknown battery, empty (database not seeded) or
 * limitation (the page cannot run for this battery) state.
 */
export function BatteryGate({
  children,
  need,
}: {
  children: (battery: Battery) => ReactNode;
  need?: BatteryNeed;
}) {
  const { battery, error, isPending, refetch, notFound, requested } =
    useDefaultBattery();

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

  if (notFound) {
    return (
      <EmptyState title="Battery not found">
        <p>
          No battery <code>{requested}</code> exists in this database. Choose
          one in the battery selector, or open the{" "}
          <Link to={{ search: "" }}>default battery</Link>.
        </p>
      </EmptyState>
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

  const blocked =
    (need === "analysis" && !battery.analysis.available) ||
    (need === "measurements" && battery.incomplete_cycle_count > 0);
  if (need && blocked) return <LimitationState battery={battery} need={need} />;

  return <>{children(battery)}</>;
}
