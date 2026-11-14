import type { HealthLevel, TemperatureBand } from "../api/types";

/** Accent token name (`--cy`, `--gr`, …) used for a status. */
export type Tone = "cy" | "gr" | "am" | "rd";

/**
 * Tone for the API's `health_level` (the prototype's `hcol`: ≥85% green, ≥80% amber, else red).
 * The thresholds live in the backend; the UI only maps the level to a token.
 */
export const HEALTH_TONE: Record<HealthLevel, Tone> = {
  healthy: "gr",
  caution: "am",
  critical: "rd",
};

/** Tone for the API's `temperature_band` (prototype: < 30 °C cyan, 30–40 °C amber, else red). */
export const BAND_TONE: Record<TemperatureBand, Tone> = {
  normal: "cy",
  warm: "am",
  hot: "rd",
};

export const toneColor = (tone: Tone) => `var(--${tone})`;

export const HEALTH_COLOR: Record<HealthLevel, string> = {
  healthy: toneColor(HEALTH_TONE.healthy),
  caution: toneColor(HEALTH_TONE.caution),
  critical: toneColor(HEALTH_TONE.critical),
};

export const BAND_COLOR: Record<TemperatureBand, string> = {
  normal: toneColor(BAND_TONE.normal),
  warm: toneColor(BAND_TONE.warm),
  hot: toneColor(BAND_TONE.hot),
};
