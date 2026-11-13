import type { InsightKind, Insights } from "../../api/types";
import styles from "./Overview.module.css";

/** Row label and bar colour per insight kind (legacy `meta`). */
export const INSIGHT_META: Record<
  InsightKind,
  { label: string; color: string }
> = {
  observation: { label: "Observation", color: "var(--cy)" },
  watch: { label: "Watch", color: "var(--am)" },
  note: { label: "Note", color: "var(--ib)" },
  model: { label: "Model", color: "var(--gr)" },
};

export function InsightsPanel({ insights }: { insights: Insights }) {
  return (
    <>
      <div className="lb">Intelligence insights</div>
      <p className={`mu ${styles.insightsNote}`}>
        Rule-based findings from the analysis API
      </p>
      {insights.insights.map((insight) => {
        const meta = INSIGHT_META[insight.kind];
        return (
          <div key={insight.kind} className={styles.insight}>
            <i
              className={styles.insightBar}
              style={{ background: meta.color }}
              aria-hidden="true"
            />
            <div>
              <div className="lb" style={{ color: meta.color }}>
                {meta.label}
              </div>
              <p className={styles.insightText} data-testid="insight-text">
                {insight.text}
              </p>
            </div>
          </div>
        );
      })}
    </>
  );
}
