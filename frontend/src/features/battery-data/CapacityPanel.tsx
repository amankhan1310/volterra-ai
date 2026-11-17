import { describeError } from "../../api/errors";
import type { Capacity } from "../../api/types";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { Stat } from "../../components/ui/Stat";
import { ErrorState } from "../../components/ui/States";
import { fixed } from "../../lib/format";
import styles from "./BatteryData.module.css";
import type { UseQueryResult } from "@tanstack/react-query";

function CapacityFigures({ data }: { data: Capacity }) {
  const ref = data.reference;
  const trend = data.trend;
  return (
    <>
      <p className={styles.analysis}>
        <ProvenanceTag provenance={data.provenance} /> From the{" "}
        {data.provenance === "simulated" ? "simulated" : "measured"} discharge
        capacity of {data.usable_cycles} cycles
        {data.first_cycle !== null && data.last_cycle !== null
          ? ` (cycles ${String(data.first_cycle)}–${String(data.last_cycle)})`
          : ""}
        ; needs no temperature. Initial and final capacity are medians of the
        first and last 5 cycles.
      </p>
      <div className={styles.stats}>
        <Stat
          label="Initial capacity"
          value={fixed(data.initial_capacity.value, 3)}
          unit="Ah"
        />
        <Stat
          label="Final capacity"
          value={fixed(data.final_capacity.value, 3)}
          unit="Ah"
        />
        <Stat
          label="Capacity loss"
          value={fixed(data.capacity_loss.value, 3)}
          unit="Ah"
        />
        <Stat
          label="Capacity retention"
          value={fixed(data.retention.value, 1)}
          unit="%"
        />
        <Stat
          label="SOH at start"
          value={fixed(data.initial_soh.value, 1, "unavailable")}
          unit={ref ? "%" : ""}
        />
        <Stat
          label="SOH now (last 5 cycles)"
          value={fixed(data.final_soh.value, 1, "unavailable")}
          unit={ref ? "%" : ""}
        />
      </div>
      <p className={styles.analysis} data-testid="capacity-reference">
        {ref ? (
          <>
            SOH reference: <b>{fixed(ref.capacity_ah, 2)} Ah</b> (
            {ref.description}), not the first measurement.{" "}
          </>
        ) : (
          <>SOH unavailable: no stated reference capacity. </>
        )}
        {data.eol_cycle_observed !== null
          ? `Reached ${fixed(data.context.eol_pct, 0)} % SOH at cycle ${String(data.eol_cycle_observed)} (observed).`
          : data.starts_below_eol
            ? ""
            : ref
              ? `Has not reached ${fixed(data.context.eol_pct, 0)} % SOH in the recorded cycles.`
              : ""}
      </p>
      {trend ? (
        <p className={styles.analysis} data-testid="capacity-trend">
          <ProvenanceTag provenance="fitted" /> Degradation trend over{" "}
          {trend.cycles} cycles:{" "}
          <b>
            {trend.fade.value === null
              ? `${fixed(trend.slope.value, 5)} Ah/cycle`
              : `${fixed(trend.fade.value, 2)} SOH points per 100 cycles`}
          </b>{" "}
          ({fixed(trend.slope.value, 5)} Ah/cycle, R² {fixed(trend.r2, 2)}),
          fitted from {fixed(trend.start_capacity.value, 3)} to{" "}
          {fixed(trend.end_capacity.value, 3)} Ah. It describes the recorded
          cycles only and is not extrapolated.
        </p>
      ) : null}
      {data.limitations.length > 0 || !data.full_analytics.available ? (
        <ul className={styles.flags} aria-label="Limitations">
          {data.limitations.map((m) => (
            <li key={m}>{m}</li>
          ))}
          {data.full_analytics.available ? null : (
            <li>
              Not supported here: remaining-life forecast, anomalies, simulator
              and advisor ({data.full_analytics.message}).
            </li>
          )}
        </ul>
      ) : null}
    </>
  );
}

/** Capacity degradation and SOH of the selected battery, from its measured capacity alone. */
export function CapacityPanel({
  capacity,
}: {
  capacity: UseQueryResult<Capacity>;
}) {
  return (
    <Card data-testid="capacity-panel">
      <div className="lb">Capacity degradation and SOH</div>
      {capacity.isError ? (
        <ErrorState
          title={describeError(capacity.error).title}
          message={describeError(capacity.error).message}
          code={describeError(capacity.error).code}
          onRetry={() => void capacity.refetch()}
        />
      ) : capacity.data ? (
        <CapacityFigures data={capacity.data} />
      ) : (
        <QueryFallback
          queries={[capacity]}
          label="Loading capacity analysis"
          height={160}
        />
      )}
    </Card>
  );
}
