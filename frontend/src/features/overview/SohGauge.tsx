import { useEffect, useId, useState } from "react";
import { fixed } from "../../lib/format";
import styles from "./Overview.module.css";

const OUTER_R = 118;
const INNER_R = 96;
export const OUTER_C = 2 * Math.PI * OUTER_R;
export const INNER_C = 2 * Math.PI * INNER_R;

export interface Tick {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  major: boolean;
  lit: boolean;
}

/** 60 ticks around the dial; every 5th is long; lit while `k ≤ SOH × 0.6` (prototype geometry). */
export function gaugeTicks(soh: number): Tick[] {
  return Array.from({ length: 60 }, (_, k) => {
    const a = (k * 6 * Math.PI) / 180;
    const major = k % 5 === 0;
    const r1 = major ? 133 : 137;
    const round1 = (v: number) => Number(v.toFixed(1));
    return {
      x1: round1(170 + r1 * Math.sin(a)),
      y1: round1(170 - r1 * Math.cos(a)),
      x2: round1(170 + 144 * Math.sin(a)),
      y2: round1(170 - 144 * Math.cos(a)),
      major,
      lit: k <= soh * 0.6,
    };
  });
}

/** Dash offsets of the two arcs once drawn: outer = SOH, inner = life used towards EOL. */
export function arcOffsets(soh: number, lifeUsed: number) {
  return {
    outer: OUTER_C * (1 - soh / 100),
    inner: INNER_C * (1 - Math.min(1, Math.max(0, lifeUsed))),
  };
}

interface SohGaugeProps {
  /** Fitted SOH now, in percent. */
  soh: number;
  /** API `life_used_fraction` (0–1) for the selected EOL threshold. */
  lifeUsed: number;
  eolPct: number;
  /** Health colour token for the gradient end. */
  color: string;
}

/** The Overview hero dial (legacy ui.js `pages.overview`); the arcs animate in on mount. */
export function SohGauge({ soh, lifeUsed, eolPct, color }: SohGaugeProps) {
  const gradient = useId();
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    // Two frames, as in the prototype, so the transition starts from the empty ring.
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => {
        setDrawn(true);
      });
    });
    return () => {
      cancelAnimationFrame(first);
      cancelAnimationFrame(second);
    };
  }, []);
  const target = arcOffsets(soh, lifeUsed);
  const sohText = fixed(soh, 1);

  return (
    <svg
      viewBox="0 0 340 340"
      width="100%"
      className={styles.gauge}
      role="img"
      aria-label={`State of health ${sohText} percent`}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--cy)" />
          <stop offset="1" stopColor={color} />
        </linearGradient>
      </defs>
      {gaugeTicks(soh).map((t, k) => (
        <line
          key={k}
          x1={t.x1}
          y1={t.y1}
          x2={t.x2}
          y2={t.y2}
          stroke={t.lit ? "var(--cy)" : "var(--bd-strong)"}
          strokeOpacity={t.lit ? 0.75 : 1}
          strokeWidth={t.major ? 1.6 : 1}
        />
      ))}
      <g transform="rotate(-90 170 170)">
        <circle
          cx="170"
          cy="170"
          r={OUTER_R}
          fill="none"
          stroke="var(--el)"
          strokeWidth="12"
        />
        <circle
          className={styles.arc}
          data-testid="gauge-outer"
          cx="170"
          cy="170"
          r={OUTER_R}
          fill="none"
          stroke={`url(#${gradient})`}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={OUTER_C}
          strokeDashoffset={drawn ? target.outer : OUTER_C}
        />
        <circle
          cx="170"
          cy="170"
          r={INNER_R}
          fill="none"
          stroke="var(--el)"
          strokeWidth="4"
        />
        <circle
          className={styles.arc}
          data-testid="gauge-inner"
          cx="170"
          cy="170"
          r={INNER_R}
          fill="none"
          stroke="var(--ib)"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={INNER_C}
          strokeDashoffset={drawn ? target.inner : INNER_C}
        />
      </g>
      <text
        x="170"
        y="182"
        textAnchor="middle"
        fill="var(--tx)"
        fontSize="58"
        fontWeight="800"
      >
        {sohText}
        <tspan fontSize="24" fill="var(--mu)">
          %
        </tspan>
      </text>
      <text
        x="170"
        y="208"
        textAnchor="middle"
        fill="var(--mu)"
        fontSize="11"
        letterSpacing="1.5"
      >
        STATE OF HEALTH
      </text>
      <text x="170" y="250" textAnchor="middle" fill="var(--ib)" fontSize="10">
        inner ring: life used to {eolPct}% threshold
      </text>
    </svg>
  );
}
