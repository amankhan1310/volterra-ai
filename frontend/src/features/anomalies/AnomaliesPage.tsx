import { useMemo } from "react";
import { useAnomalies, useCycles } from "../../api/hooks";
import type { Anomalies, Battery, Cycles } from "../../api/types";
import { getPage } from "../../app/pages";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { ResultNotes } from "../../components/ui/ResultNotes";
import { V1_NOTE } from "../overview/AboutTheseResults";
import { AnomalyTimeline } from "./AnomalyTimeline";
import styles from "./Anomalies.module.css";
import {
  CHANNEL_CHARTS,
  SEVERITY_LABEL,
  channelOption,
  eventValue,
  expectedRange,
  severityRule,
  type ChannelChart,
} from "./options";

function ChannelCard({
  chart,
  cycles,
  anomalies,
}: {
  chart: ChannelChart;
  cycles: Cycles;
  anomalies: Anomalies;
}) {
  const theme = useChartTheme();
  const option = useMemo(
    () => channelOption(theme, chart, cycles.items, anomalies.events),
    [theme, chart, cycles, anomalies],
  );
  const flagged = anomalies.events.filter((e) => e.channel === chart.channel);
  const flaggedCycles = new Set(flagged.map((e) => e.cycle));
  return (
    <Card className={styles.half}>
      <div className="lb">{chart.label}</div>
      <EChart
        option={option}
        height={260}
        label={`${chart.label} per cycle with ${String(flagged.length)} flagged events.`}
      />
      <ChartDataTable
        caption={`${chart.label} per cycle with flagged events (${chart.unit})`}
        columns={["Cycle", `${chart.label} (${chart.unit})`, "Flagged"]}
        rows={cycles.items.map((c) => [
          String(c.cycle),
          c[chart.field].toFixed(chart.dp),
          flaggedCycles.has(c.cycle) ? "Yes" : "",
        ])}
      />
    </Card>
  );
}

function EventsTable({ anomalies }: { anomalies: Anomalies }) {
  const { events, method } = anomalies;
  return (
    <Card className={styles.tableCard}>
      <div className={`lb ${styles.tableTitle}`}>Detected events</div>
      {events.length ? (
        <div
          className={styles.scroll}
          tabIndex={0}
          aria-label="Detected events table, scrolls sideways"
        >
          <table className={styles.table} data-testid="events-table">
            <thead>
              <tr>
                <th scope="col">Cycle</th>
                <th scope="col">Type</th>
                <th scope="col">Value</th>
                <th scope="col">Expected range</th>
                <th scope="col">Severity</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={`${e.channel}-${String(e.cycle)}`}>
                  <td>{e.cycle}</td>
                  <td>{e.type}</td>
                  <td>{eventValue(e)}</td>
                  <td>{expectedRange(e)}</td>
                  <td
                    className={
                      e.severity === "high" ? styles.high : styles.medium
                    }
                  >
                    {SEVERITY_LABEL[e.severity]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mu">
          No anomalies at this threshold. Lower the threshold or load more data
          to keep monitoring.
        </p>
      )}
      <p className={`mu ${styles.footnote}`}>
        Flagged when a value sits more than {method.flag_threshold_abs_z} robust
        standard deviations from the median.
      </p>
    </Card>
  );
}

function AnomaliesContent({ battery }: { battery: Battery }) {
  const anomalies = useAnomalies(battery.id);
  const cycles = useCycles(battery.id);
  if (!anomalies.data || !cycles.data)
    return (
      <QueryFallback
        queries={[anomalies, cycles]}
        label="Loading anomaly detection"
        height={420}
      />
    );
  const a = anomalies.data;
  const total = a.summary.total;
  const lastCycle = cycles.data.items.at(-1)?.cycle ?? 0;
  return (
    <>
      <div className={styles.grid}>
        <Card className={styles.summary} data-testid="page-content">
          <div className="lb">Events flagged</div>
          <div
            className="big xl"
            style={{ color: total ? "var(--am)" : "var(--gr)" }}
            data-testid="events-total"
          >
            {total}
          </div>
          <p className="mu" data-testid="severity-counts">
            <b style={{ color: "var(--rd)" }}>{a.summary.high}</b> high ·{" "}
            <b style={{ color: "var(--am)" }}>{a.summary.medium}</b> medium
          </p>
          <p className={`mu ${styles.rule}`}>{severityRule(a.method)}</p>
          <p className={styles.tags}>
            <ProvenanceTag provenance={a.provenance}>
              Detected: robust z-score ({a.detector.version})
            </ProvenanceTag>
          </p>
        </Card>
        <Card className={styles.timeline}>
          <div className="lb">Timeline</div>
          <AnomalyTimeline events={a.events} lastCycle={lastCycle} />
        </Card>
      </div>
      <div className={styles.grid}>
        {CHANNEL_CHARTS.map((chart) => (
          <ChannelCard
            key={chart.channel}
            chart={chart}
            cycles={cycles.data}
            anomalies={a}
          />
        ))}
      </div>
      <EventsTable anomalies={a} />
      <ResultNotes
        items={[
          "Temperature follows a slow periodic pattern. The detector compares every value with the median of the whole series, so a spike that happens in a cool phase can stay inside the normal band and be missed.",
          "Capacity-step flags compare SOH with its rolling median. Small steps near the noise level and the last few cycles, where the window is cut short, can be flagged although nothing unusual happened.",
          "The capacity-step check uses a window centred on each cycle, so it reads later cycles. That suits looking back over history, not live alerting.",
          V1_NOTE,
        ]}
      />
    </>
  );
}

export function AnomaliesPage() {
  const page = getPage("anom");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <AnomaliesContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
