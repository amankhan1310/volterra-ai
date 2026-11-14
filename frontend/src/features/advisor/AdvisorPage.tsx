import { useAdvisor, useSimulatorConfig } from "../../api/hooks";
import type { Advisor, AdvisorRow, Battery } from "../../api/types";
import { getPage } from "../../app/pages";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Card } from "../../components/ui/Card";
import { Note } from "../../components/ui/Note";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { ResultNotes } from "../../components/ui/ResultNotes";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { V1_NOTE } from "../overview/AboutTheseResults";
import { cyclesText } from "../simulator/options";
import styles from "./Advisor.module.css";

/**
 * Diverging bar of one row (prototype geometry): half-width = min(50, |Δ%| / 2) % of the track,
 * growing right from the centre for longer life and left for shorter life.
 */
export function barGeometry(deltaPct: number): {
  left: number;
  width: number;
  positive: boolean;
} {
  const width = Math.min(50, Math.abs(deltaPct) / 2);
  const positive = deltaPct >= 0;
  return { left: positive ? 50 : 50 - width, width, positive };
}

/** "+74%" / "-43%" / "0%" with the prototype's colour rule (green only when strictly positive). */
export function deltaText(deltaPct: number): { text: string; color: string } {
  return {
    text: `${deltaPct > 0 ? "+" : ""}${deltaPct.toFixed(0)}%`,
    color: deltaPct > 0 ? "var(--gr)" : "var(--rd)",
  };
}

/**
 * Plain-language chip for a change v1 cannot compare (decision D4: no defect code here). The
 * prototype reports 0 % when a cycle count is beyond the 5000-cycle horizon or is 0 (already at
 * end of life); v1 keeps that, so the chip says why the 0 % is not a real "no effect".
 */
export function compareNotice(
  cycles: number | null,
  subject = "change",
): string | null {
  if (cycles === null) return `Beyond 5000 cycles · ${subject} shown as 0%`;
  if (cycles === 0) return `Already at end of life · ${subject} shown as 0%`;
  return null;
}

const NOTICE_TITLE =
  "The current (v1) method reports 0% when cycles to end of life cannot be compared. See About for details.";

/** "Baseline · 25 °C · 1C · 80% DoD from 86.1% SOH" from the API's baseline conditions. */
export function baselineLabel(advisor: Advisor): string {
  const b = advisor.baseline_conditions;
  return `Baseline · ${String(b.temp_c)} °C · ${String(b.c_rate)}C · ${String(b.dod_pct)}% DoD from ${String(advisor.start_soh_pct)}% SOH`;
}

function SensitivityRow({
  row,
  baselineComparable,
}: {
  row: AdvisorRow;
  baselineComparable: boolean;
}) {
  const bar = barGeometry(row.delta_pct);
  const delta = deltaText(row.delta_pct);
  // When the baseline itself cannot be compared, the baseline card carries the single chip.
  const notice = baselineComparable ? compareNotice(row.cycles_to_eol) : null;
  return (
    <div className={styles.row} data-testid="advisor-row">
      <div>
        <b>{row.change}</b>
        <div className={`mu ${styles.why}`}>{row.why}</div>
        {notice ? (
          <div className={styles.notice}>
            <ProvenanceTag tone="amber" title={NOTICE_TITLE}>
              <span data-testid="advisor-row-notice">{notice}</span>
            </ProvenanceTag>
          </div>
        ) : null}
      </div>
      <div
        className={styles.bar}
        role="img"
        aria-label={`${delta.text} versus baseline`}
      >
        <i
          data-testid="advisor-bar"
          style={{
            left: `${String(bar.left)}%`,
            width: `${String(bar.width)}%`,
            background: bar.positive ? "var(--gr)" : "var(--rd)",
          }}
        />
      </div>
      <div className={styles.value}>
        <b data-testid="advisor-cycles">{cyclesText(row.cycles_to_eol)}</b>{" "}
        <span style={{ color: delta.color }} data-testid="advisor-delta">
          {delta.text}
        </span>
      </div>
    </div>
  );
}

function AdvisorContent({ battery }: { battery: Battery }) {
  const draft = useScenarioDraft();
  const config = useSimulatorConfig(battery.id);
  const eol = draft.params?.eol_pct;
  const start = draft.params?.start_soh_pct;
  const advisor = useAdvisor(battery.id, eol, start);
  if (!advisor.data)
    return (
      <QueryFallback
        queries={[config, advisor]}
        label="Loading the charging advisor"
        height={420}
      />
    );
  const a = advisor.data;
  const changed = draft.changed;
  const baselineNotice = compareNotice(
    a.baseline_cycles_to_eol,
    "every change",
  );
  return (
    <>
      <Card className={styles.baseline} data-testid="page-content">
        <div className="lb" data-testid="advisor-baseline-label">
          {baselineLabel(a)}
        </div>
        <div
          className="big xl"
          style={{ color: "var(--cy)" }}
          data-testid="advisor-baseline"
        >
          {cyclesText(a.baseline_cycles_to_eol)}
          <small>cycles to {a.eol_pct}% SOH</small>
        </div>
        <p className={styles.tags}>
          <ProvenanceTag provenance={a.provenance}>
            Simulated estimate
          </ProvenanceTag>{" "}
          <ProvenanceTag provenance="assumed">
            Coefficients assumed
          </ProvenanceTag>
          {changed.eolPct ? (
            <>
              {" "}
              <ProvenanceTag title="Set on the What-If Simulator page; reloading the app restores the default.">
                EOL threshold {a.eol_pct}% · set in the Simulator
              </ProvenanceTag>
            </>
          ) : null}
          {changed.startSohPct ? (
            <>
              {" "}
              <ProvenanceTag title="Set on the What-If Simulator page; reloading the app restores the default.">
                Initial SOH {a.start_soh_pct}% · set in the Simulator
              </ProvenanceTag>
            </>
          ) : null}
          {baselineNotice ? (
            <>
              {" "}
              <ProvenanceTag tone="amber" title={NOTICE_TITLE}>
                <span data-testid="advisor-baseline-notice">
                  {baselineNotice}
                </span>
              </ProvenanceTag>
            </>
          ) : null}
        </p>
      </Card>
      <Card>
        {a.rows.map((row) => (
          <SensitivityRow
            key={row.change}
            row={row}
            baselineComparable={baselineNotice === null}
          />
        ))}
      </Card>
      <Note>{a.note}</Note>
      <ResultNotes
        items={[
          "When cycles to end of life cannot be compared (beyond 5000 cycles, or already at end of life because the initial SOH is at or below the threshold), this version shows the change as 0% instead of saying so.",
          "The temperature, charging-rate and depth-of-discharge effects use assumed coefficients, so the rows show direction and relative size, not guaranteed gains.",
          V1_NOTE,
        ]}
      />
    </>
  );
}

export function AdvisorPage() {
  const page = getPage("advisor");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <AdvisorContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
