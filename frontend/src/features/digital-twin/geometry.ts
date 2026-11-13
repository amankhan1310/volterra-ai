/**
 * Isometric pack drawing from the prototype (legacy/ui.js `twInit`): modules are 40 × 40 × 26
 * blocks on a 48-unit pitch, six per row, projected with `Q(x, y, z)`.
 */
const SIZE = 40;
const HEIGHT = 26;
const PITCH = 48;
export const PER_ROW = 6;

/** Isometric projection: "x,y" with one decimal, as the prototype formats it. */
export function project(x: number, y: number, z: number): string {
  return `${((x - y) * 0.866).toFixed(1)},${((x + y) * 0.5 - z).toFixed(1)}`;
}

const poly = (...points: [number, number, number][]) =>
  points.map(([x, y, z]) => project(x, y, z)).join(" ");

/** Base plate under all modules (the prototype's 24-module plate is 300 × 204). */
export function platePoints(count: number): string {
  const rows = Math.max(1, Math.ceil(count / PER_ROW));
  const right = PER_ROW * PITCH + 2;
  const bottom = rows * PITCH + 2;
  return poly(
    [-10, -10, 0],
    [right, -10, 0],
    [right, bottom, 0],
    [-10, bottom, 0],
  );
}

export interface ModuleFaces {
  /** Front-left face. */
  left: string;
  /** Front-right face. */
  right: string;
  top: string;
}

export function moduleFaces(index: number): ModuleFaces {
  const x = (index % PER_ROW) * PITCH;
  const y = Math.floor(index / PER_ROW) * PITCH;
  const a = SIZE;
  const h = HEIGHT;
  return {
    left: poly(
      [x, y + a, 0],
      [x + a, y + a, 0],
      [x + a, y + a, h],
      [x, y + a, h],
    ),
    right: poly(
      [x + a, y, 0],
      [x + a, y + a, 0],
      [x + a, y + a, h],
      [x + a, y, h],
    ),
    top: poly([x, y, h], [x + a, y, h], [x + a, y + a, h], [x, y + a, h]),
  };
}
