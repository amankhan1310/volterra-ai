import { useNavigate } from "react-router";
import { useAnomalies, useDefaultBattery } from "../../api/hooks";
import type { Battery } from "../../api/types";
import { describeError } from "../../api/errors";
import { PAGES, type PageMeta } from "../../app/pages";
import { cx } from "../../lib/cx";
import { PROVENANCE_LABEL, ProvenanceTag } from "../ui/ProvenanceTag";
import { useToast } from "../ui/Toast";
import styles from "./Header.module.css";
import { useTheme } from "../../state/theme";
import { BellIcon, BurgerIcon, CollapseIcon, MoonIcon, SunIcon } from "./icons";
import { SIDEBAR_ID } from "./Sidebar";

interface HeaderProps {
  page: PageMeta | undefined;
  drawerOpen: boolean;
  onToggleDrawer: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNavigate: () => void;
}

export function Header({
  page,
  drawerOpen,
  onToggleDrawer,
  collapsed,
  onToggleCollapse,
  onNavigate,
}: HeaderProps) {
  return (
    <header className={styles.hd}>
      <button
        type="button"
        className={cx(styles.ib, styles.burger)}
        aria-label={drawerOpen ? "Close menu" : "Open menu"}
        aria-expanded={drawerOpen}
        aria-controls={SIDEBAR_ID}
        onClick={onToggleDrawer}
      >
        <BurgerIcon />
      </button>
      <button
        type="button"
        className={cx(styles.ib, styles.collapse)}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
        aria-controls={SIDEBAR_ID}
        onClick={onToggleCollapse}
      >
        <CollapseIcon />
      </button>
      <nav aria-label="Breadcrumb" className={styles.crumb}>
        <span className={cx("mu", styles.workspace)}>Workspace</span>{" "}
        <span className={cx("mu", styles.workspace)} aria-hidden="true">
          /
        </span>{" "}
        <b aria-current="page">{page?.label ?? "Page not found"}</b>
      </nav>
      <div className={styles.fx} />
      <QuickNav page={page} onNavigate={onNavigate} />
      <DataSourceTag />
      <ThemeToggle />
      <NotificationBell />
    </header>
  );
}

function QuickNav({
  page,
  onNavigate,
}: {
  page: PageMeta | undefined;
  onNavigate: () => void;
}) {
  const navigate = useNavigate();
  return (
    <select
      className={styles.qn}
      aria-label="Quick navigation"
      value={page?.path ?? ""}
      onChange={(e) => {
        onNavigate();
        void navigate(e.target.value);
      }}
    >
      {page ? null : (
        <option value="" disabled>
          Go to…
        </option>
      )}
      {PAGES.map((p) => (
        <option key={p.key} value={p.path}>
          {p.label}
        </option>
      ))}
    </select>
  );
}

/** Legacy header pill "Simulated · 2.0 Ah cell profile", built from the API's battery record. */
export function dataSourceLabel(battery: Battery): string {
  return `${PROVENANCE_LABEL[battery.data_provenance]} · ${battery.nominal_capacity_ah.toFixed(1)} Ah cell profile`;
}

function DataSourceTag() {
  const { battery } = useDefaultBattery();
  if (!battery) return null;
  const title = battery.is_synthetic
    ? "Seeded synthetic data, not a real vehicle"
    : `Measured data from ${battery.dataset_name}`;
  return (
    <span className={styles.tag}>
      <ProvenanceTag provenance={battery.data_provenance} title={title}>
        {dataSourceLabel(battery)}
      </ProvenanceTag>
    </span>
  );
}

/** Legacy notification bell: the badge counts flagged anomaly events; clicking explains it. */
/** Light/dark switch (D2): a toggle button, pressed in light; the icon shows the other theme. */
function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const light = theme === "light";
  return (
    <button
      type="button"
      className={styles.ib}
      aria-label="Light theme"
      aria-pressed={light}
      title={light ? "Switch to dark theme" : "Switch to light theme"}
      onClick={toggle}
    >
      {light ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}

function NotificationBell() {
  const { battery } = useDefaultBattery();
  const anomalies = useAnomalies(battery?.id);
  const toast = useToast();
  // Read during render: TanStack Query only re-renders for result fields the render used.
  const total = anomalies.data?.summary.total;
  const failure = anomalies.isError
    ? describeError(anomalies.error).message
    : null;

  const onClick = () => {
    if (total !== undefined) {
      toast(
        `${total} anomaly events flagged in the dataset. Open Anomaly Detection to review.`,
      );
    } else if (failure !== null) {
      toast(`Anomaly count unavailable: ${failure}`);
    } else {
      toast("The anomaly count is still loading.");
    }
  };

  return (
    <button
      type="button"
      className={styles.ib}
      aria-label={
        total === undefined
          ? "Notifications"
          : `Notifications: ${total} anomaly events flagged`
      }
      onClick={onClick}
    >
      <BellIcon />
      {total === undefined ? null : (
        <span className={styles.bdg} aria-hidden="true">
          {total}
        </span>
      )}
    </button>
  );
}
