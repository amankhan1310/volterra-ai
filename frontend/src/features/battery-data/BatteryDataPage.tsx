import { useMemo, useState } from "react";
import { describeError } from "../../api/errors";
import { useCycleSamples, useCycles } from "../../api/hooks";
import type { Battery, Cycle } from "../../api/types";
import { getPage } from "../../app/pages";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { BatterySelect } from "../../components/layout/BatterySelect";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { Segmented } from "../../components/ui/Segmented";
import { Stat } from "../../components/ui/Stat";
import { ErrorState } from "../../components/ui/States";
import { fixed } from "../../lib/format";
import styles from "./BatteryData.module.css";
import { RulPanel } from "./RulPanel";
import {
  CYCLE_CHANNELS,
  SAMPLE_CHANNELS,
  cycleChartOption,
  cyclePoints,
  measuredCycleChannels,
  sampleChartOption,
  samplePoints,
  type CycleChannel,
  type SampleChannel,
} from "./options";

function BatteryFacts({ battery }: { battery: Battery }) {
  return (
    <Card data-testid="page-content">
      <div className={styles.head}>
        <div>
          <div className="lb">Battery</div>
          <p className={styles.title}>
            <b data-testid="data-battery">{battery.external_id}</b> ·{" "}
            {battery.dataset_name}{" "}
            <ProvenanceTag provenance={battery.data_provenance} />
          </p>
        </div>
        <div className={styles.picker}>
          <span className="lb" aria-hidden="true">
            Choose battery
          </span>
          <BatterySelect className={styles.select} label="Choose battery" />
        </div>
      </div>
      <div className={styles.stats}>
        <Stat label="Chemistry" value={battery.chemistry ?? "not stated"} />
        <Stat label="Form factor" value={battery.form_factor ?? "not stated"} />
        <Stat
          label="Rated capacity"
          value={fixed(battery.nominal_capacity_ah, 2)}
          unit="Ah"
        />
        <Stat label="Cycles" value={String(battery.cycle_count)} />
        <Stat
          label="Without temperature or voltage"
          value={String(battery.incomplete_cycle_count)}
        />
        <Stat
          label="Flagged cycles"
          value={String(battery.flagged_cycle_count)}
        />
      </div>
      <p className={styles.analysis} data-testid="data-analysis">
        {battery.analysis.available
          ? battery.is_synthetic
            ? "Analytics available: this is the synthetic reference battery the methods were developed on."
            : "Analytics available. They were developed on the synthetic reference pack and are not validated on real cells."
          : `Analytics unavailable: ${battery.analysis.message ?? ""}`}
      </p>
      {battery.flags.length > 0 ? (
        <ul className={styles.flags} aria-label="Source notes">
          {battery.flags.map((f) => (
            <li key={f.code}>
              <code>{f.code}</code>: {f.detail}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function CycleChart({ cycles }: { cycles: readonly Cycle[] }) {
  const theme = useChartTheme();
  const { measured, missing } = useMemo(
    () => measuredCycleChannels(cycles),
    [cycles],
  );
  const [choice, setChoice] = useState<CycleChannel>("capacity_ah");
  const channel = measured.includes(choice) ? choice : "capacity_ah";
  const meta = CYCLE_CHANNELS[channel];
  const points = useMemo(() => cyclePoints(cycles, channel), [cycles, channel]);
  const flagged = useMemo(
    () =>
      cyclePoints(
        cycles.filter((c) => c.quality_flags.length > 0),
        channel,
      ),
    [cycles, channel],
  );
  const option = useMemo(
    () => cycleChartOption(theme, points, channel, flagged),
    [theme, points, channel, flagged],
  );
  return (
    <Card>
      <div className={styles.toolbar}>
        <div className="lb">Per-cycle measurements</div>
        <Segmented
          label="Cycle channel"
          options={measured.map((k) => ({
            value: k,
            label: CYCLE_CHANNELS[k].label,
          }))}
          value={channel}
          onChange={setChoice}
        />
      </div>
      <EChart
        option={option}
        height={300}
        label={`${meta.label} (${meta.unit}) over ${String(points.length)} measured cycles, ${String(flagged.length)} flagged.`}
      />
      {missing.length > 0 ? (
        <p className="mu" data-testid="data-not-measured">
          Not measured for this battery (left empty, never filled in):{" "}
          {missing.map((k) => CYCLE_CHANNELS[k].label.toLowerCase()).join(", ")}
          .
        </p>
      ) : null}
      <ChartDataTable
        caption={`${meta.label} per cycle (${meta.unit})`}
        columns={["Cycle", `${meta.label} (${meta.unit})`, "Flags"]}
        rows={cycles.map((c) => [
          String(c.cycle),
          c[channel]?.toFixed(meta.dp) ?? "not measured",
          c.quality_flags.join(", "),
        ])}
      />
    </Card>
  );
}

function SampleChart({
  battery,
  cycles,
}: {
  battery: Battery;
  cycles: readonly Cycle[];
}) {
  const theme = useChartTheme();
  const first = cycles[0]?.cycle ?? 0;
  const last = cycles[cycles.length - 1]?.cycle ?? 0;
  const [requested, setRequested] = useState(last);
  const known = cycles.some((c) => c.cycle === requested);
  const samples = useCycleSamples(
    battery.is_synthetic || !known ? undefined : battery.id,
    requested,
  );
  const [channel, setChannel] = useState<SampleChannel>("voltage_v");
  const meta = SAMPLE_CHANNELS[channel];
  const points = useMemo(
    () => (samples.data ? samplePoints(samples.data, channel) : []),
    [samples.data, channel],
  );
  const option = useMemo(
    () => sampleChartOption(theme, points, channel),
    [theme, points, channel],
  );

  if (battery.is_synthetic) {
    return (
      <Card>
        <div className="lb">Cycle samples</div>
        <p className="mu" data-testid="samples-synthetic">
          The synthetic dataset has cycle summaries only; there are no measured
          samples to show.
        </p>
      </Card>
    );
  }

  const data = samples.data;
  return (
    <Card>
      <div className={styles.toolbar}>
        <label className={styles.cycle}>
          <span className="lb">Cycle samples</span>
          <input
            type="number"
            min={first}
            max={last}
            value={requested}
            aria-label="Cycle number"
            aria-invalid={!known}
            onChange={(e) => {
              setRequested(Number(e.target.value));
            }}
          />
        </label>
        <Segmented
          label="Sample channel"
          options={(Object.keys(SAMPLE_CHANNELS) as SampleChannel[]).map(
            (k) => ({ value: k, label: SAMPLE_CHANNELS[k].label }),
          )}
          value={channel}
          onChange={setChannel}
        />
      </div>
      {!known ? (
        <p role="alert" className={styles.warn}>
          Cycle {requested} is not in this battery&apos;s data (cycles {first}–
          {last}
          {cycles.length < last - first + 1 ? ", with gaps" : ""}).
        </p>
      ) : samples.isError ? (
        <ErrorState
          title={describeError(samples.error).title}
          message={describeError(samples.error).message}
          code={describeError(samples.error).code}
          onRetry={() => void samples.refetch()}
        />
      ) : !data ? (
        <QueryFallback
          queries={[samples]}
          label="Loading cycle samples"
          height={300}
        />
      ) : (
        <>
          <EChart
            option={option}
            height={300}
            label={`${meta.label} (${meta.unit}) against time in cycle ${String(data.cycle)}, ${String(points.length)} points.`}
          />
          <p className="mu" data-testid="samples-note">
            Cycle {data.cycle}: {data.returned_samples} of {data.total_samples}{" "}
            measured samples
            {data.downsampled
              ? " (evenly downsampled for the chart; first and last kept)"
              : ""}
            .
            {points.length < data.returned_samples
              ? ` ${String(data.returned_samples - points.length)} samples have no ${meta.label.toLowerCase()} value.`
              : ""}
          </p>
          <ChartDataTable
            caption={`${meta.label} samples of cycle ${String(data.cycle)} (${meta.unit})`}
            columns={["Time (s)", `${meta.label} (${meta.unit})`]}
            rows={points.map(([t, v]) => [t.toFixed(1), v.toFixed(meta.dp)])}
          />
        </>
      )}
    </Card>
  );
}

function BatteryDataContent({ battery }: { battery: Battery }) {
  const cycles = useCycles(battery.id);
  return (
    <div className={styles.stack}>
      <BatteryFacts battery={battery} />
      {cycles.data ? (
        <>
          <CycleChart cycles={cycles.data.items} />
          {/* Keyed by battery: a battery switch starts from that battery's last cycle. */}
          <SampleChart
            key={battery.id}
            battery={battery}
            cycles={cycles.data.items}
          />
          <RulPanel battery={battery} />
        </>
      ) : (
        <QueryFallback
          queries={[cycles]}
          label="Loading cycle data"
          height={300}
        />
      )}
    </div>
  );
}

export function BatteryDataPage() {
  const page = getPage("data");
  return (
    <>
      <PageHeader title={page.title} subtitle={page.subtitle} />
      <ContextBar />
      <BatteryGate>
        {(battery) => <BatteryDataContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
