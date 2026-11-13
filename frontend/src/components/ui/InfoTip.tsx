import { useId, useState, type ReactNode } from "react";
import { cx } from "../../lib/cx";
import styles from "./InfoTip.module.css";

interface InfoTipProps {
  tip: string;
  children: ReactNode;
}

/**
 * Explanatory tooltip. Replaces the legacy `title=` tooltips (plan §2.2): it opens on hover and
 * on keyboard focus, is linked with `aria-describedby`, and Escape dismisses it.
 */
export function InfoTip({ tip, children }: InfoTipProps) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  return (
    <span
      className={cx(styles.tip, dismissed && styles.dismissed)}
      tabIndex={0}
      aria-describedby={id}
      onKeyDown={(e) => {
        if (e.key === "Escape") setDismissed(true);
      }}
      onBlur={() => {
        setDismissed(false);
      }}
      onMouseLeave={() => {
        setDismissed(false);
      }}
    >
      {children}
      <span role="tooltip" id={id} className={styles.bubble}>
        {tip}
      </span>
    </span>
  );
}
