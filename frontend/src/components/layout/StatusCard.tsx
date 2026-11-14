import { useDefaultBattery, useHealth } from "../../api/hooks";
import type { Battery, Health } from "../../api/types";
import { cx } from "../../lib/cx";
import styles from "./StatusCard.module.css";

export type ServiceStatus = "checking" | "online" | "degraded" | "offline";

/** API and database availability (U8), from `GET /health`. */
export function serviceStatus(
  health: Health | undefined,
  failed: boolean,
): { status: ServiceStatus; text: string } {
  if (failed) return { status: "offline", text: "API unreachable" };
  if (!health) return { status: "checking", text: "Checking API…" };
  switch (health.database.status) {
    case "ok":
      return { status: "online", text: "API and database online" };
    case "not_configured":
      return {
        status: "degraded",
        text: "API online · database not configured",
      };
    default:
      return { status: "degraded", text: "API online · database unavailable" };
  }
}

/** The data-source lines of the legacy status card ("Simulation mode / Seeded dataset · no vehicle link"). */
export function dataSourceText(battery: Battery | null | undefined): {
  title: string;
  detail: string;
} {
  if (battery === undefined)
    return { title: "Data source", detail: "Not loaded" };
  if (battery === null)
    return { title: "No data", detail: "No battery in the database" };
  if (battery.is_synthetic)
    return {
      title: "Simulation mode",
      detail: "Seeded dataset · no vehicle link",
    };
  return {
    title: "Measured data",
    detail: `${battery.dataset_name} · no vehicle link`,
  };
}

export function StatusCard() {
  const health = useHealth();
  const { battery } = useDefaultBattery();
  const service = serviceStatus(health.data, health.isError);
  const source = dataSourceText(battery);

  return (
    <div
      className={styles.card}
      role="group"
      aria-label="System status"
      title={service.text}
    >
      <div>
        <i
          className={cx(styles.dot, styles[service.status], "graphic")}
          aria-hidden="true"
        />
        <span className={styles.title}>{source.title}</span>
      </div>
      <small className={styles.detail}>{source.detail}</small>
      <small className={styles.service} data-status={service.status}>
        <span className="visually-hidden">Service status: </span>
        {service.text}
      </small>
    </div>
  );
}
