import type { APIRequestContext, Page } from "@playwright/test";
import type { Anomalies, Battery } from "../src/api/types";

export { PAGES } from "../src/app/pages";

/** Live values from the real API (through the dev/preview proxy), for assertions. */
export async function liveData(
  request: APIRequestContext,
): Promise<{ battery: Battery; anomalies: Anomalies }> {
  const batteries = (await (await request.get("/api/v1/batteries")).json()) as {
    items: Battery[];
  };
  const battery = batteries.items[0];
  if (!battery)
    throw new Error(
      "The database has no battery; seed it (python -m app.db.seed).",
    );
  const anomalies = (await (
    await request.get(`/api/v1/batteries/${battery.id}/anomalies`)
  ).json()) as Anomalies;
  return { battery, anomalies };
}

/** Waits until a page has settled on content or a data state (not a loading skeleton). */
export async function settled(page: Page): Promise<void> {
  await page
    .locator('[data-testid="page-placeholder"], [role="alert"]')
    .first()
    .waitFor();
}

export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
}
