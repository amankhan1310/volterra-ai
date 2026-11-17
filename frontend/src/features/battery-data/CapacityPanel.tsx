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

/** A stat whose value may be withheld by the API (null): shown as "withheld", without a unit. */
function MaybeStat({
  label,
  value,
  dp,
  unit,
  missing = "withheld",
}: {
  label: string;
  value: number | null;
  dp: number;
  unit: string;
  missing?: string;
}) {
  return (
    <Stat
      label={label}
      value={fixed(value, dp, missing)}
      unit={value === null ? "" : unit}
    />
  );
}

function CapacityFigures({ data }: { data: Capacity }) {
  const ref = data.reference;
  const trend = data.trend;
  const noSoh = ref ? "withheld" : "unavailable";
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
      <div className={styles.stats} data-testid="capacity-measured">
        <MaybeStat
          label="Initial capacity"
          value={data.initial_capacity.value}
          dp={3}
          unit="Ah"
        />
        <MaybeStat
          label="Final capacity"
          value={data.final_capacity.value}
          dp={3}
          unit="Ah"
        />
        <MaybeStat
          label="Capacity loss"
          value={data.capacity_loss.value}
          dp={3}
          unit="Ah"
        />
        <MaybeStat
          label="Capacity retention"
          value={data.retention.value}
          dp={1}
          unit="%"
        />
        <MaybeStat
          label="SOH at start"
          value={data.initial_soh.value}
          dp={1}
          unit="%"
          missing={noSoh}
        />
        <MaybeStat
          label="SOH now (last 5 cycles)"
          value={data.final_soh.value}
          dp={1}
          unit="%"
          missing={ref ? "n/a" : "unavailable"}
        />
      </div>
      {data.start_to_end_withheld ? (
        <p className={styles.analysis} data-testid="capacity-withheld">
          Some start-to-end figures are withheld because this recording is not
          one continuous fade; the reason is listed below. No measurement has
          been changed or removed.
        </p>
      ) : null}
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
          : data.starts_below_eol === false
            ? `Has not reached ${fixed(data.context.eol_pct, 0)} % SOH in the recorded cycles.`
            : ""}
      </p>
      {trend ? (
        <div className={styles.analysis} data-testid="capacity-trend">
          <p className={styles.trendHead}>
            <ProvenanceTag provenance="fitted" /> Fitted straight line: a model,
            not a measurement
          </p>
          <p className={styles.trendText}>
            Average fade over {trend.cycles} cycles:{" "}
            <b>
              {trend.fade.value === null
                ? `${fixed(trend.slope.value, 5)} Ah/cycle`
                : `${fixed(trend.fade.value, 2)} SOH points per 100 cycles`}
            </b>{" "}
            ({fixed(trend.slope.value, 5)} Ah/cycle; R² {fixed(trend.r2, 2)},
            where 1 means the points lie exactly on the line). The line runs
            from{" "}
            <span data-testid="trend-line-start">
              {fixed(trend.start_capacity.value, 3)} Ah
            </span>{" "}
            at cycle {trend.start_cycle} to{" "}
            <span data-testid="trend-line-end">
              {fixed(trend.end_capacity.value, 3)} Ah
            </span>{" "}
            at cycle {trend.end_cycle}: these are values of the line, not
            measured capacities (measured final capacity:{" "}
            <b data-testid="trend-measured-final">
              {fixed(data.final_capacity.value, 3)} Ah
            </b>
            ). A straight line averages the whole recording, so it cannot follow
            a fade that speeds up or slows down, and it is never extrapolated
            beyond the recorded cycles.
          </p>
        </div>
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
