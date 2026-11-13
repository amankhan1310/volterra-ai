import type { HealthLevel } from "../api/types";

/**
 * Colour for the API's `health_level` (the prototype's `hcol`: ≥85% green, ≥80% amber, else red).
 * The thresholds live in the backend; the UI only maps the level to a token.
 */
export const HEALTH_COLOR: Record<HealthLevel, string> = {
  healthy: "var(--gr)",
  caution: "var(--am)",
  critical: "var(--rd)",
};
