import { useSimulatorEvidence } from "../../api/hooks";
import type {
  ScenarioParams,
  SimulatorEvidence as Evidence,
} from "../../api/types";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { fixed } from "../../lib/format";
import styles from "./SimulatorEvidence.module.css";

const METHOD_LABEL: Record<string, string> = {
  v1_overview_linear: "v1 linear (Overview v1)",
  v1_simulator_baseline: "v1 simulator baseline (this page)",
  v2_quadratic: "v2 quadratic (Overview v2 = simulator v2 baseline)",
};

const range = (v: readonly number[], dp: number) =>
  `${fixed(v[0], dp)}–${fixed(v[1], dp)}`;

/** Where a scenario leaves the conditions any dataset covered (text only; nothing is recomputed). */
export function outOfDataRange(
  params: ScenarioParams,
  evidence: Evidence,
): string[] {
  const [lowT, highT] = evidence.stress.temperature.evidence.temperatures_c;
  const out: string[] = [];
  if (lowT !== undefined && highT !== undefined) {
    if (params.temp_c < lowT || params.temp_c > highT)
      out.push(
        `${String(params.temp_c)} °C is outside the ${String(lowT)}–${String(highT)} °C the matched NASA cells cover: the temperature effect here is an assumption only.`,
      );
  }
  out.push(
    `C-rate ${String(params.c_rate)}C: no dataset varies the cycling C-rate in this range (Severson covers ${range(evidence.stress.c_rate.evidence.charge_c_rate_range, 1)} C fast charging of LFP cells only).`,
  );
  if (params.dod_pct !== 100)
    out.push(
      "Depth of discharge: not varied in any dataset; its effect is assumed.",
    );
  return out;
}

function EvidenceBody({
  evidence,
  params,
}: {
  evidence: Evidence;
  params: ScenarioParams;
}) {
  const t = evidence.stress.temperature;
  const c = evidence.stress.c_rate;
  const v = evidence.baseline_validation;
  const fractions = Object.keys(Object.values(v.results)[0] ?? {});
  return (
    <>
      <p className={styles.lead}>{evidence.note}</p>
      <ul className={styles.list} data-testid="scenario-range">
        {outOfDataRange(params, evidence).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <dl className={styles.facts}>
        <div data-testid="evidence-temperature">
          <dt>
            Temperature <ProvenanceTag provenance="assumed" />
          </dt>
          <dd>
            Assumed exp({fixed(t.assumed_exp_per_c, 2)}·ΔT): ×
            {fixed(t.evidence.assumed_factor_for_this_delta, 2)} from{" "}
            {fixed(t.evidence.temperatures_c[0], 0)} to{" "}
            {fixed(t.evidence.temperatures_c[1], 0)} °C. Matched NASA cells (
            {t.evidence.pairs.length} pairs) faded ×
            {fixed(t.evidence.observed_ratio, 2)} faster (90% CI{" "}
            {range(t.evidence.observed_ratio_ci90, 2)}):{" "}
            {t.evidence.assumed_within_ci
              ? "consistent with the assumption"
              : "not consistent with the assumption"}
            , but {t.evidence.confounder}, so this is not a calibration. Read as
            temperature alone it would mean{" "}
            {fixed(t.evidence.implied_exp_per_c_if_all_temperature, 3)}/°C (90%
            CI {range(t.evidence.implied_exp_per_c_ci90, 3)}):{" "}
            <span data-testid="evidence-temperature-use">{t.evidence.use}</span>
            .
          </dd>
        </div>
        <div data-testid="evidence-c-rate">
          <dt>
            C-rate <ProvenanceTag provenance="assumed" />
          </dt>
          <dd>
            Assumed ×{fixed(c.evidence.assumed_fade_factor_per_extra_c, 2)} fade
            per extra C. Severson ({c.evidence.cells} cells,{" "}
            {c.evidence.applies_to}): life ×
            {fixed(c.evidence.life_factor_per_extra_c, 2)} per extra C (90% CI{" "}
            {range(c.evidence.life_factor_per_extra_c_ci90, 2)}, R²{" "}
            {fixed(c.evidence.r2, 2)}). Outside the slider&apos;s range, so not
            applied.
          </dd>
        </div>
        <div>
          <dt>
            Depth of discharge <ProvenanceTag provenance="assumed" />
          </dt>
          <dd>{evidence.stress.dod.note}</dd>
        </div>
      </dl>
      <div
        className={styles.scroll}
        tabIndex={0}
        aria-label="Baseline validation, scrolls sideways"
      >
        <table className={styles.table} data-testid="baseline-validation">
          <caption>
            Baseline against real life: mean absolute error in cycles of
            remaining life, {v.cells} {v.dataset} cells, by how much of their
            life had passed
          </caption>
          <thead>
            <tr>
              <th scope="col">Method</th>
              {fractions.map((f) => (
                <th key={f} scope="col">
                  {fixed(Number(f) * 100, 0)}% of life
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(v.results).map(([method, byFraction]) => (
              <tr key={method}>
                <th scope="row">{METHOD_LABEL[method] ?? method}</th>
                {fractions.map((f) => {
                  const m = byFraction[f];
                  return (
                    <td key={f}>
                      {fixed(m?.mae_cycles, 0)}
                      {m && m.no_estimate > 0
                        ? ` (${String(m.no_estimate)} none)`
                        : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mu">
        Before the knee the trend-based baseline misses the life real cells had
        by hundreds of cycles. Read the scenario curves as relative comparisons
        between conditions, not as life predictions; for real cells, see the
        experimental RUL model on Battery Data. {v.note}
      </p>
    </>
  );
}

/** Phase 8: what the data say about the simulator's assumptions and baseline. */
export function SimulatorEvidence({ params }: { params: ScenarioParams }) {
  const evidence = useSimulatorEvidence();
  return (
    <Card data-testid="simulator-evidence">
      <h2 className="lb">Evidence behind this simulator</h2>
      {evidence.data ? (
        <EvidenceBody evidence={evidence.data} params={params} />
      ) : (
        <QueryFallback
          queries={[evidence]}
          label="Loading the simulator evidence"
          height={160}
        />
      )}
    </Card>
  );
}
