import type { PageKey } from "../../app/pages";

/**
 * The known limitations of the v1 methods (ARCHITECTURE_PLAN.md §3.6), in plain language. v1
 * reproduces the original prototype exactly, so these are kept on purpose and fixed later as
 * separately tested v2 methods. The About page is the only place that shows the codes (decision
 * D4); other pages explain the same limits without them. The API marks affected responses with
 * `known_issues` (for example F1, F2 and F7 on anomalies, F8 on the advisor).
 *
 * This is documentation, not data: no numbers here, so nothing can drift from the API's results.
 */
export interface Limitation {
  code: `F${number}`;
  title: string;
  text: string;
  pages: readonly PageKey[];
}

export const LIMITATIONS: readonly Limitation[] = [
  {
    code: "F1",
    title: "Temperature spikes can be missed",
    text: "The detector compares every temperature with the median of the whole series. The slow periodic pattern widens the normal band, so a spike during a cool phase can stay inside it.",
    pages: ["anom"],
  },
  {
    code: "F2",
    title: "Capacity-step flags can be false alarms",
    text: "Small steps near the noise level are flagged, and so are the last cycles, where the comparison window is cut short. The synthetic data contains no real capacity steps.",
    pages: ["anom"],
  },
  {
    code: "F3",
    title: "The fit interval on remaining life is too narrow",
    text: "It reflects only the uncertainty of the fitted slope, not measurement noise or the curvature of the fade. The backtest error points to a range several times wider.",
    pages: ["overview"],
  },
  {
    code: "F4",
    title: "Overview and Simulator differ on the same conditions",
    text: "At the baseline conditions the Simulator reaches end of life sooner than the Overview forecast, because it adds an acceleration term and starts from a rounded SOH.",
    pages: ["overview", "sim"],
  },
  {
    code: "F5",
    title: "One insight always says fade is accelerating",
    text: "The “Watch” insight does not check the numbers. The condition panel does: it warns only when recent fade exceeds 1.2 times the early-life fade.",
    pages: ["overview"],
  },
  {
    code: "F6",
    title: "Straight-line forecasts are optimistic",
    text: "Fade on this battery bends downward over its life, so a linear fit over recent cycles overestimates remaining life more the further ahead it looks.",
    pages: ["overview"],
  },
  {
    code: "F7",
    title: "The capacity-step check looks ahead",
    text: "Its window is centred on each cycle, so it reads later cycles. That suits looking back over history, not live alerting.",
    pages: ["anom"],
  },
  {
    code: "F8",
    title: "Changes that cannot be compared show 0%",
    text: "When cycles to end of life are beyond 5000 or already 0, the Advisor reports the change as 0% instead of saying it cannot be compared. The page marks these rows.",
    pages: ["advisor"],
  },
];
