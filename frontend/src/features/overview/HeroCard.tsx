import type { Backtest, Summary } from "../../api/types";
import { Card } from "../../components/ui/Card";
import { InfoTip } from "../../components/ui/InfoTip";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { Stat } from "../../components/ui/Stat";
import { fixed, roundedOr } from "../../lib/format";
import { HEALTH_COLOR } from "../../lib/health";
import styles from "./Overview.module.css";
import { SohGauge } from "./SohGauge";

/** Number of cycles in the trend fit (the prototype's "latest 120 cycles"). */
export function fitWindow(summary: Summary): number {
  return summary.trend.fit_to_cycle - summary.trend.fit_from_cycle + 1;
}

/** Shown only when the Simulator moved the EOL threshold away from its default (U1). */
export function EolChip({ eolPct }: { eolPct: number }) {
  return (
    <ProvenanceTag title="Set on the What-If Simulator page; reloading the app restores the default.">
      EOL threshold {eolPct}% · set in the Simulator
    </ProvenanceTag>
  );
}

interface HeroCardProps {
  summary: Summary;
  backtest: Backtest;
  eolPct: number;
  eolChanged: boolean;
}

/** SOH gauge and condition panel (legacy `.card.hg`). */
export function HeroCard({
  summary,
  backtest,
  eolPct,
  eolChanged,
}: HeroCardProps) {
  const color = HEALTH_COLOR[summary.health_level];
  const { rul } = summary;
  const dataWord =
    summary.context.data_provenance === "measured" ? "measured" : "simulated";
  const level = Math.round(rul.level * 100);
  return (
    <Card className={styles.hero} data-testid="page-content">
      <div className={styles.heroGauge}>
        <SohGauge
          soh={summary.soh_now.value ?? NaN}
          lifeUsed={summary.life_used_fraction.value ?? 0}
          eolPct={eolPct}
          color={color}
        />
      </div>
      <div className={styles.heroPanel}>
        <div className="lb">Battery condition</div>
        <div
          className={styles.condition}
          style={{ color }}
          data-testid="condition"
        >
          {summary.condition}
        </div>
        <p className={`mu ${styles.explain}`} data-testid="explain">
          The estimate is a straight-line fit over the latest{" "}
          {fitWindow(summary)} cycles of the {dataWord} dataset.
          {summary.acceleration.note}
        </p>
        <div className={styles.rul}>
          <div className="lb">Remaining useful life</div>
          <div
            className="big xl"
            style={{ color: "var(--cy)" }}
            data-testid="rul"
          >
            {roundedOr(rul.point, "n/a")}
            <small>cycles to {eolPct}% SOH</small>
          </div>
          {eolChanged ? (
            <div className={styles.chipRow}>
              <EolChip eolPct={eolPct} />
            </div>
          ) : null}
        </div>
        <div className={styles.stats} data-testid="hero-stats">
          <Stat
            label="Fade rate"
            value={fixed(summary.fade_rate.value, 3)}
            unit="%/cycle"
          />
          <Stat
            label={
              <InfoTip tip="Slope ±1.96 standard errors. Captures fit noise only.">
                {level}% fit interval
              </InfoTip>
            }
            value={`${roundedOr(rul.lower, "–")}–${roundedOr(rul.upper, "–")}`}
            unit="cycles"
          />
          <Stat
            label={
              <InfoTip
                tip={`Straight-line forecast scored on the held-out final ${String(backtest.test.to_cycle - backtest.test.from_cycle + 1)} cycles.`}
              >
                Backtest MAE
              </InfoTip>
            }
            value={fixed(backtest.mae.value, 2)}
            unit="SOH pts"
          />
        </div>
        <div className={styles.tags}>
          <ProvenanceTag provenance={summary.context.data_provenance}>
            {dataWord === "measured" ? "Measured data" : "Simulated data"}
          </ProvenanceTag>
          <ProvenanceTag provenance={summary.trend.provenance}>
            Fitted: linear trend
          </ProvenanceTag>
          <ProvenanceTag provenance={rul.provenance}>Predicted</ProvenanceTag>
        </div>
      </div>
    </Card>
  );
}
