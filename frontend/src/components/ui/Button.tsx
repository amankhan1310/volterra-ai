import type { ComponentPropsWithoutRef } from "react";
import { cx } from "../../lib/cx";
import styles from "./Button.module.css";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  /** `primary` = cyan→indigo gradient (legacy `.btn`); `outline` = legacy `.btn.o`. */
  variant?: "primary" | "outline";
}

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        styles.btn,
        variant === "outline" && styles.outline,
        className,
      )}
      {...rest}
    />
  );
}
