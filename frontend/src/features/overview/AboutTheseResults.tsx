import type { Backtest } from "../../api/types";
import { ResultNotes } from "../../components/ui/ResultNotes";
import { fixed } from "../../lib/format";

/** Shared closing sentence of every page's "About these results". */
export const V1_NOTE =
  "These are known limits of the current (v1) method, kept so results match the original prototype. Improved methods come in a later phase.";

/**
 * Plain-language limits of the v1 results on this page (decisions U3 and D4: no defect codes
 * here; the About page lists them).
 */
export function AboutTheseResults({ backtest }: { backtest: Backtest }) {
  return (
    <ResultNotes
      items={[
        <>
          The fit interval only reflects uncertainty in the fitted slope. It
          leaves out measurement noise and the curvature of the fade, so the
          real uncertainty is wider: the backtest error of{" "}
          {fixed(backtest.mae.value, 2)} SOH points suggests a range several
          times larger.
        </>,
        "The forecast is a straight line, but fade on this battery bends downward over its life. Forecasts more than a few dozen cycles ahead are therefore likely to be optimistic.",
        "The “Watch” insight always describes fade as accelerating, without checking the numbers. The condition panel does check: it adds its warning only when recent fade exceeds 1.2 times the early-life fade.",
        V1_NOTE,
      ]}
    />
  );
}
