import { useModels } from "../../api/hooks";
import type {
  MetricSet,
  ModelCandidate,
  ModelTask,
  Models,
} from "../../api/types";
import { getPage } from "../../app/pages";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { EmptyState } from "../../components/ui/States";
import { fixed } from "../../lib/format";
import styles from "./Models.module.css";

/** Held-out test sets smaller than this are reported, but flagged as not a stable estimate. */
export const MIN_STABLE_TEST_BATTERIES = 3;

type Run = NonNullable<Models["run"]>;

/** Human name and error unit of a task (the run's task keys are stable identifiers). */
export function taskLabel(task: ModelTask): { title: string; unit: string } {
  if (task.task === "rul")
    return { title: "Remaining useful life", unit: "cycles" };
  if (task.task === "rul_cross_dataset")
    return {
      title:
        "Cross-dataset stress test: remaining useful life, trained on Severson only",
      unit: "cycles",
    };
  if (task.kind === "forecast")
    return {
      title: `SOH forecast, ${String(task.horizon_cycles)} cycles ahead`,
      unit: "SOH points",
    };
  return {
    title: `SOH estimation from measured signals (${task.task.replace(/^soh_/, "")})`,
    unit: "SOH points",
  };
}

const num = (v: number | null | undefined, dp: number) => fixed(v, dp, "–");

function cvCell(m: MetricSet, dp: number) {
  const folds = m.batteries_per_fold?.join("/") ?? "";
  return `${num(m.mae, dp)} (${String(m.batteries ?? 0)} batt.${folds ? `; folds ${folds}` : ""})`;
}

function RunCard({ run, note }: { run: Run; note: string }) {
  const check = run.label_check;
  return (
    <Card data-testid="page-content">
      <div className={styles.head}>
        <h2 className={styles.title}>
          Run <code data-testid="run-id">{run.run_id}</code>
        </h2>
        <ProvenanceTag tone="amber" title="Not production-validated">
          Experimental
        </ProvenanceTag>
      </div>
      <p className={styles.note}>{note}</p>
      <dl className={styles.facts}>
        <div>
          <dt>Trained</dt>
          <dd>{new Date(run.trained_at).toISOString().slice(0, 10)}</dd>
        </div>
        <div>
          <dt>Splits</dt>
          <dd>{run.split_rule}</dd>
        </div>
        <div>
          <dt>End of life</dt>
          <dd>{run.eol_definition}</dd>
        </div>
        <div>
          <dt>Intervals</dt>
          <dd>
            Split-conformal, {num(run.interval_level * 100, 0)}% nominal,
            calibrated on held-out batteries
          </dd>
        </div>
      </dl>
      <p className={styles.note} data-testid="how-to-read">
        <b>How to read the tables.</b> Cross-validation: out-of-fold errors over
        the training batteries in 5 battery-grouped folds (fold sizes shown);
        used to choose the model. Held-out test: batteries never used for
        training, calibration or model choice, scored once. Coverage and width
        use intervals calibrated on separate calibration batteries. Errors on a
        few batteries vary a lot from one battery to the next.
      </p>
      <p className={styles.note}>
        Data: {run.datasets.map((d) => `${d.dataset} ${d.version}`).join(", ")}{" "}
        (public laboratory datasets; provenance and licences on the Battery Data
        and About pages). Code {run.code_sha256?.slice(0, 12) ?? "unknown"},
        libraries{" "}
        {Object.entries(run.libraries)
          .map(([k, v]) => `${k} ${v}`)
          .join(", ")}
        .
      </p>
      {check.labelled_cells > 0 ? (
        <p className={styles.note} data-testid="label-check">
          Source EOL labels: {check.labelled_cells} cells. The threshold rule
          agrees on {check.rule_finds_eol} (largest difference{" "}
          {num(check.rule_minus_label_max_abs_cycles, 0)} cycles); it finds no
          crossing on {check.rule_misses_eol}. {check.note}
        </p>
      ) : null}
      <div
        className={styles.scroll}
        tabIndex={0}
        aria-label="Dataset census, scrolls sideways"
      >
        <table className={styles.table}>
          <caption className="visually-hidden">
            Batteries per dataset and why some cannot be used
          </caption>
          <thead>
            <tr>
              <th scope="col">Dataset</th>
              <th scope="col">Batteries</th>
              <th scope="col">Excluded by source</th>
              <th scope="col">Start below EOL</th>
              <th scope="col">Censored (never reach EOL)</th>
            </tr>
          </thead>
          <tbody>
            {run.datasets.map((d) => (
              <tr key={d.dataset}>
                <td>{d.dataset}</td>
                <td>{d.batteries}</td>
                <td>{d.excluded.length}</td>
                <td>{d.start_below_eol.length}</td>
                <td>{d.censored.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function rows(task: ModelTask, dataset: string, dp: number) {
  return task.candidates.map((c: ModelCandidate) => {
    const d = c.datasets.find((x) => x.dataset === dataset);
    if (!d) return null;
    return (
      <tr
        key={`${dataset}-${c.name}`}
        className={c.selected ? styles.selected : undefined}
      >
        <td>
          {c.name}
          {c.selected ? " (selected)" : ""}
          {c.learned ? "" : " · baseline"}
        </td>
        <td>{cvCell(d.cv, dp)}</td>
        <td>{num(d.test.mae, dp)}</td>
        <td>{num(d.test.rmse, dp)}</td>
        <td>{num(d.test.r2, 2)}</td>
        <td>{num(d.test.picp, 2)}</td>
        <td>{num(d.test.mpiw, dp)}</td>
        <td>
          {d.calibration.batteries} batt. / {d.calibration.rows} rows
          {d.interval_basis === "dataset" ? "" : " (pooled)"}
        </td>
      </tr>
    );
  });
}

function TaskCard({ task }: { task: ModelTask }) {
  const { title, unit } = taskLabel(task);
  const dp = unit === "cycles" ? 0 : 2;
  const datasets = Object.entries(task.batteries_by_dataset);
  const small = datasets.filter(
    ([, n]) => n.test > 0 && n.test < MIN_STABLE_TEST_BATTERIES,
  );
  return (
    <Card data-testid={`task-${task.task}`}>
      <div className={styles.head}>
        <h2 className={styles.title}>{title}</h2>
        <span className="mu">
          Selected: <b>{task.selected_model}</b> ({task.selection_rule})
        </span>
      </div>
      <div
        className={styles.scroll}
        tabIndex={0}
        aria-label={`${title} results, scrolls sideways`}
      >
        <table className={styles.table}>
          <caption className="visually-hidden">
            {title}: errors in {unit} per dataset and model
          </caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col">Cross-validation MAE ({unit})</th>
              <th scope="col">Held-out test MAE</th>
              <th scope="col">Test RMSE</th>
              <th scope="col">Test R²</th>
              <th scope="col">Test coverage (90% nominal)</th>
              <th scope="col">Test interval width</th>
              <th scope="col">Calibration set</th>
            </tr>
          </thead>
          {datasets.map(([dataset, n]) => (
            <tbody key={dataset}>
              <tr className={styles.group}>
                <td colSpan={8}>
                  {dataset}: {n.train} train / {n.calibration} calibration /{" "}
                  {n.test} test batteries
                </td>
              </tr>
              {rows(task, dataset, dp)}
            </tbody>
          ))}
        </table>
      </div>
      {small.length > 0 ? (
        <p className={styles.warn} data-testid="small-test-warning">
          Fewer than {MIN_STABLE_TEST_BATTERIES} held-out test batteries for{" "}
          {small.map(([d]) => d).join(", ")}: those test numbers are anecdotal;
          the cross-validation column is the better guide.
        </p>
      ) : null}
      {task.task === "rul_cross_dataset" ? (
        <p className="mu">
          Trained and calibrated on Severson LFP cells only. CALCE (LiCoO₂) is a
          different chemistry; NASA&apos;s chemistry is not stated. Poor results
          here mean the model does not transfer.
        </p>
      ) : null}
    </Card>
  );
}

/** Display order: the main RUL task, the forecasts, SOH estimation, then the stress test. */
export function taskOrder(task: string): number {
  if (task === "rul") return 0;
  if (task.startsWith("forecast_h"))
    return 1 + Number(task.slice("forecast_h".length)) / 1e6;
  if (task.startsWith("soh_")) return 2;
  return 3;
}

export function ModelsContent({ models }: { models: Models }) {
  if (!models.run) {
    return (
      <EmptyState title="No model run imported">
        <p>
          Train and evaluate offline with{" "}
          <code>python -m volterra_ml.modeling run</code>, then import the run
          with <code>python -m app.db.import_models &lt;run-dir&gt;</code>.
        </p>
      </EmptyState>
    );
  }
  return (
    <div className={styles.stack}>
      <RunCard run={models.run} note={models.note} />
      {[...models.tasks]
        .sort((x, y) => taskOrder(x.task) - taskOrder(y.task))
        .map((t) => (
          <TaskCard key={t.task} task={t} />
        ))}
    </div>
  );
}

export function ModelsPage() {
  const page = getPage("models");
  const models = useModels();
  return (
    <>
      <PageHeader title={page.title} subtitle={page.subtitle} />
      {models.data ? (
        <ModelsContent models={models.data} />
      ) : (
        <QueryFallback
          queries={[models]}
          label="Loading model evaluations"
          height={300}
        />
      )}
    </>
  );
}
