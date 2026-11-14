import { describe, expect, it } from "vitest";
import tokensCss from "./tokens.css?raw";

/**
 * WCAG contrast of the design tokens in both themes (M6). Text needs 4.5:1 (1.4.3, AA);
 * graphics such as chart lines, gauge arcs, twin modules, bars and dots need 3:1 (1.4.11).
 * Read from tokens.css itself, so a palette edit that breaks contrast fails here.
 */
type Tokens = Record<string, string>;

function block(selectorStart: string): Tokens {
  const start = tokensCss.indexOf(selectorStart);
  if (start < 0) throw new Error(`No block ${selectorStart}`);
  const body = tokensCss.slice(
    tokensCss.indexOf("{", start) + 1,
    tokensCss.indexOf("}", start),
  );
  const tokens: Tokens = {};
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g))
    if (m[1] && m[2]) tokens[m[1]] = m[2].trim();
  return tokens;
}

const dark = block(":root,");
const light = { ...dark, ...block(':root[data-theme="light"]') };

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m?.[1]) throw new Error(`Not a #rrggbb colour: ${hex}`);
  const channels = [0, 2, 4].map((i) => {
    const c = parseInt(m[1]?.slice(i, i + 2) ?? "0", 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const [r = 0, g = 0, b = 0] = channels;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

const ACCENTS = ["cy", "ib", "gr", "am", "rd", "violet"];
const SURFACES = ["--card", "--el", "--bg", "--side"];

function failures(
  tokens: Tokens,
  fg: string[],
  bg: string[],
  min: number,
): string[] {
  const out: string[] = [];
  for (const f of fg)
    for (const b of bg) {
      const ratio = contrast(tokens[f] ?? "", tokens[b] ?? "");
      if (ratio < min) out.push(`${f} on ${b}: ${ratio.toFixed(2)}`);
    }
  return out;
}

describe.each([
  ["dark", dark],
  ["light", light],
])("%s theme contrast", (_name, tokens) => {
  it("text and text accents reach 4.5:1 on every surface (WCAG 1.4.3)", () => {
    const text = ["--tx", "--mu", ...ACCENTS.map((a) => `--${a}`)];
    expect(failures(tokens, text, SURFACES, 4.5)).toEqual([]);
  });

  it("sidebar group labels reach 4.5:1", () => {
    expect(
      failures(tokens, ["--group-label"], ["--side", "--bg"], 4.5),
    ).toEqual([]);
  });

  it("graphic accents reach 3:1 on every surface (WCAG 1.4.11)", () => {
    const fills = ACCENTS.map((a) => `--${a}-fill`);
    expect(failures(tokens, fills, [...SURFACES, "--twin-scene"], 3)).toEqual(
      [],
    );
  });

  it("text on accent fills (buttons, badge, chart marker) reaches 4.5:1", () => {
    expect([
      ...failures(tokens, ["--on-accent"], ["--cy", "--ib"], 4.5),
      ...failures(tokens, ["--on-danger"], ["--rd"], 4.5),
    ]).toEqual([]);
  });
});

describe("light-only drawing tokens", () => {
  it("twin module edges reach 3:1 against the pack plate", () => {
    const edges = ["cy", "gr", "am", "rd"].map(
      (t) => `--twin-module-edge-${t}`,
    );
    expect(failures(light, edges, ["--twin-plate"], 3)).toEqual([]);
  });
});

describe("dark theme is the prototype's redesign, unchanged", () => {
  it("keeps the legacy token values (ARCHITECTURE_PLAN.md §2.1)", () => {
    expect(dark).toMatchObject({
      "--bg": "#070a0f",
      "--side": "#0a0e15",
      "--card": "#0d121b",
      "--el": "#121a26",
      "--hi": "#182333",
      "--cy": "#54e7ff",
      "--ib": "#8dafff",
      "--gr": "#7cf2bc",
      "--am": "#ffc56e",
      "--rd": "#ff7185",
      "--tx": "#f5f7fc",
      "--mu": "#8998ad",
      "--bd": "#1b2638",
    });
  });

  it("uses graphic accents identical to the text accents", () => {
    for (const a of ACCENTS)
      expect(dark[`--${a}-fill`], a).toBe(dark[`--${a}`]);
  });
});
