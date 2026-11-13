/**
 * Chart colours, read from the CSS tokens at render time (plan §7: no colour literals in charts,
 * so a theme change reaches the charts too). Canvas cannot resolve `var(--x)`, hence the lookup.
 */
export interface ChartTheme {
  cy: string;
  ib: string;
  gr: string;
  am: string;
  rd: string;
  violet: string;
  tx: string;
  mu: string;
  bd: string;
  el: string;
  bdStrong: string;
  onAccent: string;
  grid: string;
  zoomFill: string;
  font: string;
}

const TOKENS: Record<keyof ChartTheme, string> = {
  cy: "--cy",
  ib: "--ib",
  gr: "--gr",
  am: "--am",
  rd: "--rd",
  violet: "--violet",
  tx: "--tx",
  mu: "--mu",
  bd: "--bd",
  el: "--el",
  bdStrong: "--bd-strong",
  onAccent: "--on-accent",
  grid: "--chart-grid",
  zoomFill: "--chart-zoom-fill",
  font: "--font",
};

export function readChartTheme(
  element: Element = document.documentElement,
): ChartTheme {
  const style = getComputedStyle(element);
  const theme = {} as ChartTheme;
  for (const [key, token] of Object.entries(TOKENS) as [
    keyof ChartTheme,
    string,
  ][]) {
    theme[key] = style.getPropertyValue(token).trim();
  }
  return theme;
}

/** `#rrggbb` plus an alpha in [0, 1] as `rgba()`; other colour syntaxes are returned unchanged. */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (!m) return color;
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h ?? "0", 16));
  return `rgba(${String(r)}, ${String(g)}, ${String(b)}, ${String(alpha)})`;
}

/** Escapes text placed into an ECharts HTML tooltip. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
