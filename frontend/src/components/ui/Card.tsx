import type { ComponentPropsWithoutRef } from "react";
import { cx } from "../../lib/cx";
import styles from "./Card.module.css";

interface CardProps extends ComponentPropsWithoutRef<"div"> {
  /** Lift on hover (legacy `.card.hv`). */
  hover?: boolean;
}

/** Glass surface card (legacy `.card`). */
export function Card({ hover = false, className, ...rest }: CardProps) {
  return (
    <div
      className={cx(styles.card, hover && styles.hover, className)}
      {...rest}
    />
  );
}
