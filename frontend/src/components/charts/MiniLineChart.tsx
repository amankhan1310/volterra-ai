/**
 * Small SVG line chart, a port of the prototype's `chart(ss, o)` (legacy/core.js) for one series:
 * 720 units wide, 8% padding above and below the data, five labelled grid lines, "0" and
 * "cycle N" under the axis and an optional dashed cursor at one index.
 */
const WIDTH = 720;
const PAD = { l: 44, r: 12, t: 10, b: 22 };

export interface MiniChartGeometry {
  grid: { y: number; label: string }[];
  path: string;
  cursorX: number | null;
  lastIndex: number;
}

export function miniChartGeometry(
  values: readonly number[],
  args: { height: number; cursor?: number | null; dp?: number },
): MiniChartGeometry {
  const { height, cursor = null, dp = 1 } = args;
  let lo = values.length ? Math.min(...values) : 0;
  let hi = values.length ? Math.max(...values) : 1;
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad;
  hi += pad;
  const n = values.length;
  const x = (i: number) => PAD.l + (i / (n - 1 || 1)) * (WIDTH - PAD.l - PAD.r);
  const y = (v: number) =>
    height - PAD.b - ((v - lo) / (hi - lo)) * (height - PAD.t - PAD.b);
  const grid = [0, 1, 2, 3, 4].map((k) => {
    const v = lo + ((hi - lo) * k) / 4;
    return { y: y(v), label: v.toFixed(dp) };
  });
  const path = values
    .map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
    .join("");
  return {
    grid,
    path,
    cursorX: cursor === null ? null : x(cursor),
    lastIndex: n - 1,
  };
}

interface MiniLineChartProps {
  values: readonly number[];
  color: string;
  label: string;
  height?: number;
  /** Index of the dashed cursor line. */
  cursor?: number | null;
}

export function MiniLineChart({
  values,
  color,
  label,
  height = 150,
  cursor = null,
}: MiniLineChartProps) {
  const g = miniChartGeometry(values, { height, cursor });
  return (
    <svg
      viewBox={`0 0 ${String(WIDTH)} ${String(height)}`}
      role="img"
      aria-label={label}
    >
      {g.grid.map((line, k) => (
        <g key={k}>
          <line
            x1={PAD.l}
            x2={WIDTH - PAD.r}
            y1={line.y}
            y2={line.y}
            stroke="var(--bd)"
          />
          <text
            x={PAD.l - 6}
            y={line.y + 4}
            textAnchor="end"
            fill="var(--mu)"
            fontSize="11"
          >
            {line.label}
          </text>
        </g>
      ))}
      <text x={PAD.l} y={height - 5} fill="var(--mu)" fontSize="11">
        0
      </text>
      <text
        x={WIDTH - PAD.r}
        y={height - 5}
        textAnchor="end"
        fill="var(--mu)"
        fontSize="11"
      >
        cycle {g.lastIndex}
      </text>
      {g.cursorX === null ? null : (
        <line
          data-testid="mini-chart-cursor"
          x1={g.cursorX}
          x2={g.cursorX}
          y1={PAD.t}
          y2={height - PAD.b}
          stroke="var(--mu)"
          strokeDasharray="2 4"
        />
      )}
      <path
        d={g.path}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}
