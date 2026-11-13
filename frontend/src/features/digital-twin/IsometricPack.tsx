import type { KeyboardEvent } from "react";
import styles from "./DigitalTwin.module.css";
import { moduleFaces, platePoints } from "./geometry";

interface IsometricPackProps {
  /** Number of modules to draw (the API's `modules.count`). */
  count: number;
  /** Fill for every module: the pack value, since modules are illustrative. */
  color: string;
  selected: number | null;
  onSelect: (index: number) => void;
}

/**
 * The prototype's isometric pack. Each module is a focusable toggle button that responds to
 * Enter and Space (the prototype handled Enter only).
 */
export function IsometricPack({
  count,
  color,
  selected,
  onSelect,
}: IsometricPackProps) {
  const onKeyDown = (index: number) => (e: KeyboardEvent<SVGGElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(index);
    }
  };
  return (
    <svg
      className={styles.pack}
      viewBox="-200 -50 480 320"
      role="group"
      aria-label={`Isometric battery pack of ${String(count)} illustrative modules`}
    >
      <polygon
        points={platePoints(count)}
        fill="var(--twin-plate)"
        stroke="var(--twin-plate-edge)"
      />
      {Array.from({ length: count }, (_, k) => {
        const faces = moduleFaces(k);
        const on = k === selected;
        return (
          <g
            key={k}
            className={styles.module}
            data-selected={on}
            role="button"
            tabIndex={0}
            aria-label={`Module ${String(k + 1)}`}
            aria-pressed={on}
            onClick={() => {
              onSelect(k);
            }}
            onKeyDown={onKeyDown(k)}
          >
            <polygon className={styles.left} points={faces.left} fill={color} />
            <polygon
              className={styles.right}
              points={faces.right}
              fill={color}
            />
            <polygon
              className={styles.top}
              points={faces.top}
              fill={color}
              stroke={on ? "var(--tx)" : "var(--twin-edge)"}
            />
          </g>
        );
      })}
    </svg>
  );
}
