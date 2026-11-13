import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  title: string;
  subtitle: string;
  actions?: ReactNode;
}

/** Gradient title, subtitle and actions (legacy `head(t, s)`). */
export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className={styles.top}>
      <div>
        <h1>{title}</h1>
        <p className={styles.subtitle}>{subtitle}</p>
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}
