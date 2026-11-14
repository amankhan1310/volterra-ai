import { useEffect, useRef, useState } from "react";
import type { AnomalyEvent } from "../../api/types";
import {
  LANES,
  SEVERITY_COLOR,
  SEVERITY_LABEL,
  TIMELINE,
  laneY,
  timelineX,
} from "./options";
import styles from "./Anomalies.module.css";

/** Accessible description of one event (also its tooltip text). */
export function eventLabel(e: AnomalyEvent): string {
  return `Cycle ${String(e.cycle)}: ${e.type}, ${SEVERITY_LABEL[e.severity].toLowerCase()} severity`;
}

/**
 * Width to draw at: the container's, measured, so one SVG unit is one pixel and text stays 11 px
 * (the prototype's fixed 720-unit drawing shrank to unreadable text on a phone). Below
 * `TIMELINE.minWidth` the drawing keeps that width and scrolls inside its card.
 */
function useDrawWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number>(TIMELINE.width);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      if (el.clientWidth > 0)
        setWidth(Math.max(TIMELINE.minWidth, Math.floor(el.clientWidth)));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, []);
  return { ref, width };
}

/**
 * Three-lane event timeline (prototype SVG). Each event dot is focusable and shows its tooltip on
 * hover or keyboard focus; the prototype relied on a native `<title>` only.
 */
export function AnomalyTimeline({
  events,
  lastCycle,
}: {
  events: readonly AnomalyEvent[];
  lastCycle: number;
}) {
  const [active, setActive] = useState<AnomalyEvent | null>(null);
  const { ref, width } = useDrawWidth();
  const tipX = active ? timelineX(active.cycle, lastCycle, width) : 0;
  const tipY = active
    ? laneY(LANES.findIndex((l) => l.channel === active.channel))
    : 0;
  const tipText = active ? eventLabel(active) : "";
  const tipW = tipText.length * 5.6 + 16;
  const tipLeft = Math.max(Math.min(tipX - tipW / 2, width - tipW), 0);
  // Above the dot, except on the top lane where there is no room: then below it.
  const tipTop = tipY < 40 ? tipY + 10 : tipY - 30;
  return (
    <div ref={ref} className={styles.track}>
      <svg
        className="graphic"
        viewBox={`0 0 ${String(width)} ${String(TIMELINE.height)}`}
        width={width}
        height={TIMELINE.height}
        role="group"
        aria-label="Anomaly timeline"
      >
        {LANES.map((lane, i) => {
          const y = laneY(i);
          return (
            <g key={lane.channel}>
              <text x="0" y={y + 4} fill="var(--mu)" fontSize="11">
                {lane.label}
              </text>
              <line
                x1={TIMELINE.left}
                x2={width - TIMELINE.right}
                y1={y}
                y2={y}
                stroke="var(--bd)"
              />
              {events
                .filter((e) => e.channel === lane.channel)
                .map((e) => (
                  <circle
                    key={`${e.channel}-${String(e.cycle)}`}
                    data-testid="timeline-event"
                    data-cycle={e.cycle}
                    data-channel={e.channel}
                    cx={timelineX(e.cycle, lastCycle, width)}
                    cy={y}
                    r="5"
                    fill={SEVERITY_COLOR[e.severity]}
                    tabIndex={0}
                    role="img"
                    aria-label={eventLabel(e)}
                    onMouseEnter={() => {
                      setActive(e);
                    }}
                    onMouseLeave={() => {
                      setActive(null);
                    }}
                    onFocus={() => {
                      setActive(e);
                    }}
                    onBlur={() => {
                      setActive(null);
                    }}
                  >
                    <title>{eventLabel(e)}</title>
                  </circle>
                ))}
            </g>
          );
        })}
        <text x={TIMELINE.left} y="114" fill="var(--mu)" fontSize="11">
          cycle 0
        </text>
        <text
          x={width - TIMELINE.right}
          y="114"
          textAnchor="end"
          fill="var(--mu)"
          fontSize="11"
        >
          cycle {lastCycle}
        </text>
        {active ? (
          <g pointerEvents="none" aria-hidden="true">
            <rect
              x={tipLeft}
              y={tipTop}
              width={tipW}
              height="20"
              rx="5"
              fill="var(--hi)"
              stroke="var(--bd)"
            />
            <text
              x={tipLeft + 8}
              y={tipTop + 14}
              fill="var(--tx)"
              fontSize="11"
            >
              {tipText}
            </text>
          </g>
        ) : null}
      </svg>
    </div>
  );
}
