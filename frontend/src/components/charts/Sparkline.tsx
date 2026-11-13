import styles from "./Sparkline.module.css";

/** SVG path of the prototype's sparkline (`spk`): every 4th value, scaled into 120 × 40. */
export function sparklinePath(values: readonly number[]): string {
  const s = values.filter((_, i) => i % 4 === 0);
  if (s.length === 0) return "";
  const lo = Math.min(...s);
  const hi = Math.max(...s);
  const span = hi - lo || 1;
  const last = s.length - 1 || 1;
  return s
    .map(
      (v, i) =>
        `${i ? "L" : "M"}${((i / last) * 120).toFixed(1)} ${(37 - ((v - lo) / span) * 34).toFixed(1)}`,
    )
    .join("");
}

/** Decorative trend line inside a KPI card; the card states the value itself. */
export function Sparkline({
  values,
  color,
}: {
  values: readonly number[];
  color: string;
}) {
  return (
    <svg
      className={styles.spark}
      viewBox="0 0 120 40"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d={sparklinePath(values)}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
