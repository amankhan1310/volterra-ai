import { NavLink } from "react-router";
import { NAV_GROUPS, getPage } from "../../app/pages";
import { cx } from "../../lib/cx";
import { BrandMark, PageIcon } from "./icons";
import styles from "./Sidebar.module.css";
import { StatusCard } from "./StatusCard";

export const SIDEBAR_ID = "sidebar";

interface SidebarProps {
  /** Desktop icon-only mode (legacy `aside.min`). */
  collapsed: boolean;
  /** Mobile drawer state (legacy `aside.open`). */
  drawerOpen: boolean;
  /** Mobile drawer is closed: hide it from keyboard and screen readers. */
  inert: boolean;
  onNavigate: () => void;
}

export function Sidebar({
  collapsed,
  drawerOpen,
  inert,
  onNavigate,
}: SidebarProps) {
  return (
    <aside
      id={SIDEBAR_ID}
      aria-label="Sidebar"
      className={cx(
        styles.side,
        collapsed && styles.min,
        drawerOpen && styles.open,
      )}
      inert={inert}
      data-collapsed={collapsed}
    >
      <div className={styles.logo}>
        <BrandMark />
        <div className={styles.brandText}>
          <b>VOLTERRA AI</b>
          <small>Battery Intelligence</small>
        </div>
      </div>
      <nav aria-label="Main">
        {NAV_GROUPS.map(({ group, keys }) => (
          <div key={group}>
            <div className={styles.group}>{group}</div>
            {keys.map((key) => {
              const page = getPage(key);
              return (
                <NavLink
                  key={key}
                  to={page.path}
                  className={cx(styles.link)}
                  aria-label={page.label}
                  title={collapsed ? page.label : undefined}
                  onClick={onNavigate}
                >
                  <PageIcon page={key} />
                  <span className={styles.label}>{page.label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>
      <StatusCard />
    </aside>
  );
}
