import type { ReactNode } from "react";
import styles from "./Stat.module.css";

interface StatProps {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
}

/** Label over a tabular value (legacy `.stats` / `.stats2` cells). */
export function Stat({ label, value, unit }: StatProps) {
  return (
    <div>
      <div className="lb">{label}</div>
      <b className={styles.value}>
        {value}
        {unit ? <span className={styles.unit}> {unit}</span> : null}
      </b>
    </div>
  );
}
