import type { Backtest } from "../../api/types";
import { Card } from "../../components/ui/Card";
import { fixed } from "../../lib/format";
import styles from "./Overview.module.css";

/**
 * Plain-language limits of the v1 results on this page (decisions U3 and D4: no defect codes
 * here; the About page lists them). The v1 method is kept deliberately so the numbers match the
 * prototype; improved methods are a later phase.
 */
export function AboutTheseResults({ backtest }: { backtest: Backtest }) {
  return (
    <Card className={styles.about}>
      <details>
        <summary>About these results</summary>
        <ul>
          <li>
            The fit interval only reflects uncertainty in the fitted slope. It
            leaves out measurement noise and the curvature of the fade, so the
            real uncertainty is wider: the backtest error of{" "}
            {fixed(backtest.mae.value, 2)} SOH points suggests a range several
            times larger.
          </li>
          <li>
            The forecast is a straight line, but fade on this battery bends
            downward over its life. Forecasts more than a few dozen cycles ahead
            are therefore likely to be optimistic.
          </li>
          <li>
            The “Watch” insight always describes fade as accelerating, without
            checking the numbers. The condition panel does check: it adds its
            warning only when recent fade exceeds 1.2 times the early-life fade.
          </li>
          <li>
            These are known limits of the current (v1) method, kept so results
            match the original prototype. Improved methods come in a later
            phase.
          </li>
        </ul>
      </details>
    </Card>
  );
}
