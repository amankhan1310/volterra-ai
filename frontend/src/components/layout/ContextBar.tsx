import { useDefaultBattery, useHealth } from "../../api/hooks";
import { PROVENANCE_LABEL, ProvenanceTag } from "../ui/ProvenanceTag";
import styles from "./ContextBar.module.css";

/**
 * Where the numbers on a page come from: dataset, battery, algorithm version and whether the data
 * is measured or simulated (plan §6.3; shown on every page).
 */
export function ContextBar() {
  const { battery } = useDefaultBattery();
  const health = useHealth();
  if (!battery) return null;
  return (
    <p className={styles.context} aria-label="Data context">
      <span>
        Dataset <b>{battery.dataset}</b>
      </span>
      <span aria-hidden="true">·</span>
      <span>
        Battery <b>{battery.external_id}</b>
      </span>
      {health.data ? (
        <>
          <span aria-hidden="true">·</span>
          <span>
            Algorithm <b>{health.data.algorithm_version}</b>
          </span>
        </>
      ) : null}
      <span aria-hidden="true">·</span>
      <ProvenanceTag provenance={battery.data_provenance}>
        {PROVENANCE_LABEL[battery.data_provenance]} data
      </ProvenanceTag>
    </p>
  );
}
