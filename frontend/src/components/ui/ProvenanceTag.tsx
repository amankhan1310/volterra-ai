import type { ReactNode } from "react";
import type { Provenance } from "../../api/types";
import { cx } from "../../lib/cx";
import styles from "./ProvenanceTag.module.css";

/**
 * Legacy provenance pills: amber Simulated (`.tag.s`), green Fitted (`.tag.f`), cyan Predicted
 * (`.tag.p`). `measured` and `assumed` use the neutral pill until their styles are designed.
 */
const TONE: Record<Provenance, string | undefined> = {
  simulated: styles.simulated,
  fitted: styles.fitted,
  predicted: styles.predicted,
  measured: undefined,
  assumed: undefined,
};

export const PROVENANCE_LABEL: Record<Provenance, string> = {
  measured: "Measured",
  simulated: "Simulated",
  fitted: "Fitted",
  predicted: "Predicted",
  assumed: "Assumed",
};

interface ProvenanceTagProps {
  /** Omit for the neutral pill (legacy `.tag`). */
  provenance?: Provenance;
  /**
   * Colour of a descriptive pill that is not a provenance claim, e.g. the prototype's green
   * "Pack-level" tag. Ignored when `provenance` is set.
   */
  tone?: "amber" | "green" | "cyan";
  title?: string;
  children?: ReactNode;
}

const TONE_CLASS = {
  amber: styles.simulated,
  green: styles.fitted,
  cyan: styles.predicted,
};

export function ProvenanceTag({
  provenance,
  tone,
  title,
  children,
}: ProvenanceTagProps) {
  const toneClass = provenance
    ? TONE[provenance]
    : tone
      ? TONE_CLASS[tone]
      : undefined;
  return (
    <span
      className={cx(styles.tag, toneClass)}
      data-provenance={provenance}
      title={title}
    >
      {children ?? (provenance ? PROVENANCE_LABEL[provenance] : null)}
    </span>
  );
}
