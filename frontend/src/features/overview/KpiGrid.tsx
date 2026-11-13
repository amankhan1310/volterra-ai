import type { ReactNode } from "react";
import type { Anomalies, Battery, Cycles, Summary } from "../../api/types";
import { Sparkline } from "../../components/charts/Sparkline";
import { Card } from "../../components/ui/Card";
import { InfoTip } from "../../components/ui/InfoTip";
import { cx } from "../../lib/cx";
import { fixed } from "../../lib/format";
import { fitWindow } from "./HeroCard";
import styles from "./Overview.module.css";

interface KpiCardProps {
  span: string | undefined;
  label: string;
  tip: string;
  value: ReactNode;
  unit: string;
  note: string;
  color?: string;
  extra?: ReactNode;
}

/** One KPI tile (legacy `kc(...)`): label with tooltip, large value, optional sparkline, note. */
function KpiCard({
  span,
  label,
  tip,
  value,
  unit,
  note,
  color = "var(--tx)",
  extra,
}: KpiCardProps) {
  return (
    <Card hover className={span}>
      <div className="lb">
        <InfoTip tip={tip}>{label}</InfoTip>
      </div>
      <div
        className={cx("big", styles.kpiValue)}
        style={{ color }}
        data-testid="kpi-value"
      >
        {value}
        {unit ? <small>{unit}</small> : null}
      </div>
      {extra}
      <p className={cx("mu", styles.kpiNote)} data-testid="kpi-note">
        {note}
      </p>
    </Card>
  );
}

interface KpiGridProps {
  battery: Battery;
  summary: Summary;
  cycles: Cycles;
  anomalies: Anomalies;
}

/** The six KPI cards under the hero, in the prototype's order and spans. */
export function KpiGrid({ battery, summary, cycles, anomalies }: KpiGridProps) {
  const { latest } = summary;
  const word = cycles.provenance === "measured" ? "measured" : "simulated";
  const tempEvents = anomalies.events.filter(
    (e) => e.channel === "temp",
  ).length;
  const total = summary.anomalies.total;
  return (
    <div className={styles.grid}>
      <KpiCard
        span={styles.s6}
        label="Capacity"
        tip={`Latest cycle discharge capacity (${word}).`}
        value={fixed(latest.capacity.value, 3)}
        unit="Ah"
        note={`of ${battery.nominal_capacity_ah.toFixed(1)} Ah reference`}
        extra={
          <Sparkline
            values={cycles.items.map((c) => c.capacity_ah)}
            color="var(--gr)"
          />
        }
      />
      <KpiCard
        span={styles.s6}
        label="Temperature"
        tip={`Latest cycle mean temperature (${word}).`}
        value={fixed(latest.temperature.value, 1)}
        unit="°C"
        note={`${String(tempEvents)} excursions flagged in history`}
        extra={
          <Sparkline
            values={cycles.items.map((c) => c.temp_c)}
            color="var(--cy)"
          />
        }
      />
      <KpiCard
        span={styles.s3}
        label="Voltage"
        tip={`Latest cycle mean voltage (${word}).`}
        value={fixed(latest.voltage.value, 2)}
        unit="V"
        note="drifting down with age"
      />
      <KpiCard
        span={styles.s3}
        label="Cycles"
        tip="Charge/discharge cycles in the dataset."
        value={summary.cycle_count}
        unit=""
        note={
          summary.context.is_synthetic
            ? "seeded, reproducible"
            : "in the dataset"
        }
      />
      <KpiCard
        span={styles.s3}
        label="Fade rate"
        tip="Recent SOH loss per cycle."
        value={fixed(summary.fade_rate.value, 3)}
        unit="%/cycle"
        note={`last ${String(fitWindow(summary))} cycles`}
      />
      <KpiCard
        span={styles.s3}
        label="Anomalies"
        tip="Events flagged by the robust z-score detector."
        value={total}
        unit=""
        note={`${String(summary.anomalies.high)} high severity`}
        color={total ? "var(--am)" : "var(--tx)"}
      />
    </div>
  );
}
