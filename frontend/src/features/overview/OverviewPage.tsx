import { useQueryClient } from "@tanstack/react-query";
import {
  queryKeys,
  useAnomalies,
  useBacktest,
  useCycles,
  useDefaultBattery,
  useForecast,
  useInsights,
  useSimulatorConfig,
  useSummary,
} from "../../api/hooks";
import type { Battery, Summary } from "../../api/types";
import { getPage } from "../../app/pages";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Card } from "../../components/ui/Card";
import { fixed, roundedOr } from "../../lib/format";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { AboutTheseResults } from "./AboutTheseResults";
import { DegradationTimeline } from "./DegradationTimeline";
import { HeroCard } from "./HeroCard";
import { InsightsPanel } from "./InsightsPanel";
import { KpiGrid } from "./KpiGrid";
import styles from "./Overview.module.css";
import { TelemetryExplorer } from "./TelemetryExplorer";

/** The toast detail after Run analysis: "SOH 86.1%, RUL 113 cycles" (prototype wording). */
export function resultSummary(summary: Summary): string {
  return `SOH ${fixed(summary.soh_now.value, 1)}%, RUL ${roundedOr(summary.rul.point, "n/a")} cycles`;
}

function OverviewRunAnalysis() {
  const queryClient = useQueryClient();
  const batteryId = useDefaultBattery().battery?.id;
  const eolPct = useScenarioDraft().params?.eol_pct;
  return (
    <RunAnalysisButton
      summarize={() => {
        if (batteryId === undefined || eolPct === undefined) return null;
        const summary = queryClient.getQueryData<Summary>(
          queryKeys.summary(batteryId, eolPct),
        );
        return summary ? resultSummary(summary) : null;
      }}
    />
  );
}

function OverviewContent({ battery }: { battery: Battery }) {
  const draft = useScenarioDraft();
  // The EOL threshold is shared with the Simulator (D1); it is known once its config loads.
  const config = useSimulatorConfig(battery.id);
  const eolPct = draft.params?.eol_pct;
  const summary = useSummary(battery.id, eolPct);
  const forecast = useForecast(battery.id, eolPct);
  const backtest = useBacktest(battery.id);
  const insights = useInsights(battery.id);
  const cycles = useCycles(battery.id);
  const anomalies = useAnomalies(battery.id);

  return (
    <>
      {summary.data && backtest.data && eolPct !== undefined ? (
        <HeroCard
          summary={summary.data}
          backtest={backtest.data}
          eolPct={eolPct}
          eolChanged={draft.changed.eolPct}
        />
      ) : (
        <QueryFallback
          queries={[config, summary, backtest]}
          label="Loading battery health"
          height={340}
        />
      )}

      {summary.data && cycles.data && anomalies.data ? (
        <KpiGrid
          battery={battery}
          summary={summary.data}
          cycles={cycles.data}
          anomalies={anomalies.data}
        />
      ) : (
        <div className={styles.grid}>
          <div className={styles.full}>
            <QueryFallback
              queries={[config, summary, cycles, anomalies]}
              label="Loading key indicators"
              height={150}
            />
          </div>
        </div>
      )}

      <div className={styles.grid}>
        <Card className={styles.s8}>
          {forecast.data && summary.data && eolPct !== undefined ? (
            <DegradationTimeline
              forecast={forecast.data}
              eolPct={eolPct}
              sohNow={summary.data.soh_now.value ?? NaN}
            />
          ) : (
            <QueryFallback
              queries={[config, forecast, summary]}
              label="Loading the degradation timeline"
              height={380}
            />
          )}
        </Card>
        <Card className={styles.s4}>
          {insights.data ? (
            <InsightsPanel insights={insights.data} />
          ) : (
            <QueryFallback
              queries={[insights]}
              label="Loading insights"
              height={380}
            />
          )}
        </Card>
      </div>

      <Card>
        {cycles.data && anomalies.data ? (
          <TelemetryExplorer cycles={cycles.data} anomalies={anomalies.data} />
        ) : (
          <QueryFallback
            queries={[cycles, anomalies]}
            label="Loading telemetry"
            height={320}
          />
        )}
      </Card>

      {backtest.data ? <AboutTheseResults backtest={backtest.data} /> : null}
    </>
  );
}

export function OverviewPage() {
  const page = getPage("overview");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<OverviewRunAnalysis />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <OverviewContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
