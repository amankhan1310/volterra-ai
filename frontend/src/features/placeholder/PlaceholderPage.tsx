import { getPage, type PageKey } from "../../app/pages";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Card } from "../../components/ui/Card";
import styles from "./PlaceholderPage.module.css";

/**
 * Milestone 1 stand-in for a page that a later milestone rebuilds. It says so plainly and shows
 * no numbers, so nothing here can be mistaken for an analysis result.
 */
export function PlaceholderPage({ pageKey }: { pageKey: PageKey }) {
  const page = getPage(pageKey);
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {() => (
          <Card className={styles.placeholder} data-testid="page-placeholder">
            <div className="lb">
              Placeholder · rebuilt in Milestone {page.milestone}
            </div>
            <h2 className={styles.heading}>
              {page.label} has not been rebuilt yet
            </h2>
            <p className="mu">
              This page is rebuilt in Milestone {page.milestone} of Phase 4. It
              shows no data yet, so nothing here is an analysis result. The
              original prototype in <code>legacy/</code> is the reference until
              then.
            </p>
          </Card>
        )}
      </BatteryGate>
    </>
  );
}
