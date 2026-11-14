import { Link } from "react-router";
import { useSummary } from "../../api/hooks";
import type { Battery, Summary } from "../../api/types";
import { getPage } from "../../app/pages";
import { BatteryGate } from "../../components/layout/BatteryGate";
import { ContextBar } from "../../components/layout/ContextBar";
import { PageHeader } from "../../components/layout/PageHeader";
import { QueryFallback } from "../../components/layout/QueryFallback";
import { RunAnalysisButton } from "../../components/layout/RunAnalysisButton";
import { Card } from "../../components/ui/Card";
import { ProvenanceTag } from "../../components/ui/ProvenanceTag";
import { useScenarioDraft } from "../../state/ScenarioDraftContext";
import { fitWindow } from "../overview/HeroCard";
import styles from "./About.module.css";
import { LIMITATIONS } from "./limitations";

/** The prototype's Data card, from the battery record; real data gets an honest variant. */
export function dataText(battery: Battery): string {
  const cell = `${battery.nominal_capacity_ah.toFixed(1)} Ah cell`;
  return battery.is_synthetic
    ? `${String(battery.cycle_count)} seeded synthetic cycles of a ${cell}. Reproducible, not measured from any vehicle.`
    : `${String(battery.cycle_count)} measured cycles of a ${cell} from ${battery.dataset_name}.`;
}

/** The prototype's Method card, with the nominal capacity and fit window from the API. */
export function methodText(battery: Battery, summary: Summary): string {
  return `SOH = capacity ÷ ${String(battery.nominal_capacity_ah)} Ah. RUL from a linear fit over the last ${String(fitWindow(summary))} cycles, scored by a time-ordered backtest. Anomalies by median/MAD z-score. Simulator uses assumed coefficients.`;
}

function Limitations() {
  return (
    <Card className={styles.limits}>
      <h2 className="lb" id="known-limitations">
        Known limitations of the current (v1) methods
      </h2>
      <p className={`mu ${styles.intro}`}>
        The v1 methods reproduce the original prototype exactly, so these limits
        are kept on purpose and each is fixed later as a separately tested
        method. The other pages describe them in plain language; the codes
        appear only here.
      </p>
      <ul className={styles.list} aria-labelledby="known-limitations">
        {LIMITATIONS.map((l) => (
          <li key={l.code} data-testid="limitation">
            <code className={styles.code}>{l.code}</code>
            <div>
              <b>{l.title}</b>
              <p className="mu">{l.text}</p>
              <p className={styles.where}>
                Shown on{" "}
                {l.pages.map((key, i) => {
                  const page = getPage(key);
                  return (
                    <span key={key}>
                      {i > 0 ? " and " : null}
                      <Link to={page.path}>{page.label}</Link>
                    </span>
                  );
                })}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AboutContent({ battery }: { battery: Battery }) {
  const eolPct = useScenarioDraft().params?.eol_pct;
  const summary = useSummary(battery.id, eolPct);
  if (!summary.data)
    return (
      <QueryFallback
        queries={[summary]}
        label="Loading project information"
        height={320}
      />
    );
  return (
    <>
      <div className={styles.grid}>
        <Card className={styles.third} data-testid="page-content">
          <div className="lb">Data</div>
          <p className={styles.body} data-testid="about-data">
            {dataText(battery)}
          </p>
          <p className={styles.tags}>
            <ProvenanceTag provenance={battery.data_provenance} />
          </p>
        </Card>
        <Card className={styles.third}>
          <div className="lb">Method</div>
          <p className={styles.body} data-testid="about-method">
            {methodText(battery, summary.data)}
          </p>
        </Card>
        <Card className={styles.third}>
          <div className="lb">Simulation vs a real EV</div>
          <p className={styles.body} data-testid="about-ev">
            This is a software simulation. It has no vehicle connection and does
            not replace a Battery Management System, diagnostics or warranty
            assessment.
          </p>
        </Card>
      </div>
      <Card>
        <div className="lb">Definitions</div>
        <p className={styles.body} data-testid="about-definitions">
          SOC is the present charge level. SOH is condition relative to a
          reference. RUL estimates cycles before a chosen end-of-life criterion
          and is not a guaranteed replacement date.
        </p>
        <p className="mu" data-testid="about-not-included">
          Not included yet: real-data import (CSV upload), ML model comparison,
          PDF and CSV reports, user accounts. These are later phases of the
          plan.
        </p>
      </Card>
      <Limitations />
    </>
  );
}

export function AboutPage() {
  const page = getPage("about");
  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle}
        actions={<RunAnalysisButton />}
      />
      <ContextBar />
      <BatteryGate>
        {(battery) => <AboutContent battery={battery} />}
      </BatteryGate>
    </>
  );
}
