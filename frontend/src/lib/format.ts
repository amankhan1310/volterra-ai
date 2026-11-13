/**
 * Display formatting with the prototype's exact rules. The API serialises non-finite floats as
 * the strings "NaN", "Infinity" and "-Infinity" although the OpenAPI document declares numbers,
 * so every formatter accepts both and treats anything non-finite like a missing value.
 */
export type Numeric = number | string | null | undefined;

/** A finite number, or `null` for null, undefined, NaN, ±Infinity and their string forms. */
export function finite(value: Numeric): number | null {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

/** `value.toFixed(dp)` (identical rounding to the prototype), or `fallback`. */
export function fixed(value: Numeric, dp: number, fallback = "n/a"): string {
  const n = finite(value);
  return n === null ? fallback : n.toFixed(dp);
}

/**
 * The prototype's `x ? Math.round(x) : fallback`. Zero counts as "no value" there too: an EOL
 * threshold at or above today's SOH gives an RUL of 0, which the prototype shows as "n/a".
 */
export function roundedOr(value: Numeric, fallback: string): string {
  const n = finite(value);
  return n ? String(Math.round(n)) : fallback;
}

/** Rounds to 2 decimals as a number (`+x.toFixed(2)`), the precision the prototype charts. */
export function round2(value: number): number {
  return Number(value.toFixed(2));
}
