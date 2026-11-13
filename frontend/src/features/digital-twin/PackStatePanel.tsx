import type { Cycles, Twin } from "../../api/types";
import { MiniLineChart } from "../../components/charts/MiniLineChart";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { fixed } from "../../lib/format";
import { HEALTH_COLOR } from "../../lib/health";
import styles from "./DigitalTwin.module.css";

/** The module-selection sentence (prototype wording). */
export function moduleMessage(selected: number | null): string {
  return selected === null
    ? "No module selected."
    : `Module ${String(selected + 1)}: no cell-level measurement exists, so this shows the pack value (illustrative).`;
}

interface PackStatePanelProps {
  twin: Twin;
  cycles: Cycles;
  selected: number | null;
}

/** "Pack state at cycle N": the four pack quantities, the selection note and the SOH mini chart. */
export function PackStatePanel({
  twin,
  cycles,
  selected,
}: PackStatePanelProps) {
  const { pack } = twin;
  const provenance = pack.soh.provenance;
  const stats = [
    {
      label: "SOH",
      value: fixed(pack.soh.value, 1),
      unit: "%",
      color: HEALTH_COLOR[twin.health_level],
    },
    { label: "Capacity", value: fixed(pack.capacity.value, 3), unit: "Ah" },
    {
      label: "Temperature",
      value: fixed(pack.temperature.value, 1),
      unit: "°C",
    },
    { label: "Voltage", value: fixed(pack.voltage.value, 2), unit: "V" },
  ];
  return (
    <>
      <div className="lb">Pack state at cycle {twin.cycle}</div>
      <p className={styles.tags}>
        <ProvenanceTag provenance={provenance} />{" "}
        <ProvenanceTag
          tone="green"
          title="The dataset has pack-level measurements only."
        >
          Pack-level
        </ProvenanceTag>
      </p>
      <div className={styles.stats} data-testid="pack-stats">
        {stats.map((s) => (
          <div key={s.label}>
            <div className="lb">{s.label}</div>
            <div
              className="big"
              style={s.color ? { color: s.color } : undefined}
            >
              {s.value}
              <small>{s.unit}</small>
            </div>
          </div>
        ))}
      </div>
      <p className="mu" data-testid="module-message">
        {moduleMessage(selected)}
      </p>
      <MiniLineChart
        values={cycles.items.map((c) => c.soh_pct)}
        color="var(--gr)"
        cursor={cycles.items.findIndex((c) => c.cycle === twin.cycle)}
        label={`SOH over ${String(cycles.items.length)} cycles, with cycle ${String(twin.cycle)} marked.`}
      />
    </>
  );
}
