import { useMemo } from "react";
import { Link } from "react-router";
import { ApiError } from "../../api/client";
import { describeError } from "../../api/errors";
import { useBatterySearch, useRulPredictions } from "../../api/hooks";
import type { Battery, RulPredictions } from "../../api/types";
import { ChartDataTable } from "../../components/charts/ChartDataTable";
import { EChart, useChartTheme } from "../../components/charts/EChart";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { ErrorState } from "../../components/ui/States";
import { fixed } from "../../lib/format";
import styles from "./BatteryData.module.css";
import { rulChartOption, rulSeries } from "./options";

const SPLIT_TEXT: Record<RulPredictions["split"], string> = {
  test: "Held-out test battery: the model never saw it in training or calibration.",
  calibration:
    "Calibration battery: not used for training, only to size the intervals.",
  train:
    "Training battery: these predictions are in-sample and say little about accuracy on new batteries.",
};

const INTERVAL_TEXT: Record<string, string> = {
  dataset: "split-conformal, calibrated on held-out batteries of this dataset",
  pooled:
    "split-conformal, pooled calibration: too few calibration batteries in this dataset",
};

/**
 * Before EOL the model's prediction is shown. Once the battery has reached its EOL label, its
 * remaining life is known from the data (0), so no prediction is presented for those cycles.
 */
function RulChart({ data }: { data: RulPredictions }) {
  const theme = useChartTheme();
  const before = useMemo(
    () => data.points.filter((p) => !p.past_eol),
    [data.points],
  );
  const series = useMemo(() => rulSeries(before), [before]);
  const option = useMemo(() => rulChartOption(theme, series), [theme, series]);
  const search = useBatterySearch();
  const latest = before.at(-1);
  const passed = data.points.at(-1)?.past_eol === true;
  return (
    <>
      <p className={styles.warn} role="note" data-testid="rul-warning">
        Experimental: trained and evaluated offline on public laboratory cells;
        not production-validated and not a guarantee for this battery.
      </p>
      {passed ? (
        <p className={styles.analysis} data-testid="rul-past-eol">
          This battery reached its end of life at cycle{" "}
          {fixed(data.eol_cycle, 0)} (from its measured data): no remaining life
          is predicted after that.
        </p>
      ) : null}
      {latest ? (
        <p className={styles.analysis} data-testid="rul-latest">
          {passed ? "Last prediction before EOL, at" : "At"} cycle{" "}
          {latest.cycle}: predicted remaining life{" "}
          <b>{fixed(latest.rul.point, 0)} cycles</b>, 90% interval{" "}
          {fixed(latest.rul.lower, 0)}–{fixed(latest.rul.upper, 0)} cycles (
          {INTERVAL_TEXT[data.interval_basis] ?? data.interval_basis})
          {latest.actual_rul
            ? `; actual ${fixed(latest.actual_rul.value, 0)} cycles`
            : ""}
          .
        </p>
      ) : null}
      <p className={styles.analysis} data-testid="rul-split">
        <ProvenanceTag provenance="predicted" /> {SPLIT_TEXT[data.split]}{" "}
        {data.censored
          ? "This battery never reaches EOL in its data, so its actual RUL is unknown."
          : `It reaches EOL at cycle ${fixed(data.eol_cycle, 0)}.`}
      </p>
      <EChart
        option={option}
        height={300}
        label={`Predicted remaining useful life with 90% interval at ${String(before.length)} prediction points before end of life${data.censored ? "" : ", with the actual remaining life"}.`}
      />
      <p className="mu">
        Model {data.model.model} ({data.model.status}), run {data.model.run_id}.{" "}
        {data.note} See <Link to={`/models${search}`}>Models</Link> for its
        evaluation.
      </p>
      <ChartDataTable
        caption="Predicted and actual remaining useful life (cycles)"
        columns={["Cycle", "SOH (%)", "Predicted", "90% interval", "Actual"]}
        rows={before.map((p) => [
          String(p.cycle),
          fixed(p.soh.value, 2),
          fixed(p.rul.point, 0),
          `${fixed(p.rul.lower, 0)}–${fixed(p.rul.upper, 0)}`,
          p.actual_rul ? fixed(p.actual_rul.value, 0) : "unknown",
        ])}
      />
    </>
  );
}

/** The latest model run's stored RUL predictions for a real battery (Phase 7, experimental). */
export function RulPanel({ battery }: { battery: Battery }) {
  const predictions = useRulPredictions(
    battery.is_synthetic ? undefined : battery.id,
  );
  const missing =
    predictions.error instanceof ApiError &&
    predictions.error.code === "predictions_not_found";
  return (
    <Card data-testid="rul-panel">
      <div className="lb">Remaining useful life (experimental model)</div>
      {battery.is_synthetic ? (
        <p className="mu" data-testid="rul-none">
          The models are trained on measured laboratory cells; they make no
          predictions for the synthetic reference battery.
        </p>
      ) : missing ? (
        <p className="mu" data-testid="rul-none">
          No model prediction for {battery.external_id} in the latest imported
          run.
        </p>
      ) : predictions.isError ? (
        <ErrorState
          title={describeError(predictions.error).title}
          message={describeError(predictions.error).message}
          code={describeError(predictions.error).code}
          onRetry={() => void predictions.refetch()}
        />
      ) : predictions.data ? (
        <RulChart data={predictions.data} />
      ) : (
        <QueryFallback
          queries={[predictions]}
          label="Loading model predictions"
          height={300}
        />
      )}
    </Card>
  );
}
