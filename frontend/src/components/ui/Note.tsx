import type { ReactNode } from "react";
import styles from "./Note.module.css";

/** Amber left-border disclaimer (legacy `.note`). */
export function Note({ children }: { children: ReactNode }) {
  return <div className={styles.note}>{children}</div>;
}
