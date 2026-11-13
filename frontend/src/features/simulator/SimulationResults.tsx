import type { SimulatorConfig, Simulation } from "../../api/types";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { fixed } from "../../lib/format";
import { cyclesText, deltaLine } from "./options";
import styles from "./Simulator.module.css";

const TONE = { up: "var(--gr)", down: "var(--rd)", flat: "var(--mu)" };

/** Results column (legacy `#sres`). */
export function SimulationResults({
  sim,
  config,
}: {
  sim: Simulation;
  config: SimulatorConfig;
}) {
  const delta = deltaLine(sim);
  const dataWord =
    config.context.data_provenance === "measured" ? "measured" : "simulated";
  return (
    <div
      data-testid="sim-results"
      // The parameters this result is for (lets tests wait for a debounced simulation).
      data-params={[
        sim.params.temp_c,
        sim.params.c_rate,
        sim.params.dod_pct,
        sim.params.horizon_cycles,
        sim.params.start_soh_pct,
        sim.params.eol_pct,
      ].join("|")}
    >
      <div className="lb">Estimated cycles to {sim.params.eol_pct}% SOH</div>
      <div
        className="big xl"
        style={{ color: "var(--cy)" }}
        data-testid="cycles-to-eol"
      >
        {cyclesText(sim.cycles_to_eol)}
      </div>
      <p
        className={styles.delta}
        style={{ color: TONE[delta.tone] }}
        data-testid="delta"
      >
        {delta.text}
      </p>
      <div className={styles.stats}>
        <div>
          <div className="lb">SOH after {sim.params.horizon_cycles}</div>
          <b>{fixed(sim.soh_after_horizon.value, 1)}%</b>
        </div>
        <div>
          <div className="lb">Fade rate</div>
          <b>{fixed(sim.rate.value, 3)} %/cyc</b>
        </div>
        <div>
          <div className="lb">Baseline cycles</div>
          <b>{cyclesText(sim.baseline_cycles_to_eol)}</b>
        </div>
        <div>
          <div className="lb">Baseline SOH</div>
          <b>{fixed(sim.baseline_soh_after_horizon.value, 1)}%</b>
        </div>
      </div>
      <div className="lb">Assumptions</div>
      <p className={`mu ${styles.assumptions}`} data-testid="assumptions">
        Base fade {fixed(config.base_fade.value, 3)} %/cycle fitted from the
        last 120 {dataWord} cycles; scaling coefficients are assumed.
      </p>
      <p className={styles.tags}>
        <ProvenanceTag provenance={sim.provenance}>
          Simulated estimate
        </ProvenanceTag>{" "}
        <ProvenanceTag>Uncertainty: not quantified</ProvenanceTag>
      </p>
    </div>
  );
}
