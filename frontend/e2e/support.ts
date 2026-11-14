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

/**
 * Waits until a page has settled: its content, placeholder or an error is shown, and no card is
 * still showing a loading skeleton.
 */
export async function settled(page: Page): Promise<void> {
  await page
    .locator(
      '[data-testid="page-content"], [data-testid="page-placeholder"], [role="alert"]',
    )
    .first()
    .waitFor();
  await page
    .locator('[role="status"][aria-label^="Loading"]')
    .first()
    .waitFor({ state: "detached" });
}

/** The app shell scrolls inside `<main>`; the document itself should never scroll vertically. */
export async function verticalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      document.documentElement.scrollHeight -
      document.documentElement.clientHeight,
  );
}

export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
}

/**
 * Visually hidden elements that still take up layout space (e.g. a hidden table, which treats
 * `height` as a minimum), and so can make the document scroll into empty space.
 */
export async function oversizedHidden(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll(".visually-hidden")]
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.width > 1 || r.height > 1;
      })
      .map((el) => el.textContent.slice(0, 60)),
  );
}
