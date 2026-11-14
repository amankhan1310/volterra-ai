import type { ReactNode } from "react";
import { Card } from "./Card";
import styles from "./ResultNotes.module.css";

/**
 * Collapsed "About these results" card: the plain-language limits of the v1 results shown on a
 * page (decisions U3 and D4; defect codes appear only on the About page).
 */
export function ResultNotes({
  items,
  title = "About these results",
}: {
  items: readonly ReactNode[];
  title?: string;
}) {
  return (
    <Card className={styles.notes}>
      <details>
        <summary>{title}</summary>
        <ul>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </details>
    </Card>
  );
}
