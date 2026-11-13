import type { ReactNode } from "react";
import { Button } from "./Button";
import { Card } from "./Card";
import styles from "./States.module.css";

/** Placeholder block shown while data loads. */
export function Skeleton({
  label,
  height = 120,
}: {
  label: string;
  height?: number;
}) {
  return (
    <div
      role="status"
      aria-label={label}
      className={styles.skeleton}
      style={{ height }}
    >
      <span className="visually-hidden">{label}</span>
    </div>
  );
}

interface ErrorStateProps {
  title: string;
  message: string;
  /** Machine-readable error code from the API envelope, shown for support. */
  code?: string | undefined;
  hint?: ReactNode;
  onRetry?: (() => void) | undefined;
}

export function ErrorState({
  title,
  message,
  code,
  hint,
  onRetry,
}: ErrorStateProps) {
  return (
    <Card role="alert" className={styles.error}>
      <div className="lb">{title}</div>
      <p>{message}</p>
      {hint ? <p className="mu">{hint}</p> : null}
      {code ? <p className={styles.code}>Error code: {code}</p> : null}
      {onRetry ? (
        <Button variant="outline" onClick={onRetry} className={styles.retry}>
          Retry
        </Button>
      ) : null}
    </Card>
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <Card className={styles.empty}>
      <div className="lb">{title}</div>
      <div className="mu">{children}</div>
    </Card>
  );
}
