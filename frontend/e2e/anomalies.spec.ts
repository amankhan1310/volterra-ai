import { expect, test } from "@playwright/test";
import { liveData, settled } from "./support";

test.describe("Anomaly Detection against the real API", () => {
  test("renders the live events, charts and table with no console errors", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const { anomalies } = await liveData(request);
    await page.goto("/anomalies");
    await settled(page);

    await expect(page.getByTestId("events-total")).toHaveText(
      String(anomalies.summary.total),
    );
    await expect(page.getByTestId("severity-counts")).toHaveText(
      `${String(anomalies.summary.high)} high · ${String(anomalies.summary.medium)} medium`,
    );
    await expect(page.getByTestId("timeline-event")).toHaveCount(
      anomalies.events.length,
    );
    await expect(
      page.getByTestId("events-table").locator("tbody tr"),
    ).toHaveCount(anomalies.events.length);
    for (const name of ["Temperature", "Voltage"])
      await expect(
        page
          .getByRole("img", { name: new RegExp(`^${name} per cycle with`) })
          .locator("canvas")
          .first(),
      ).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("timeline events are reachable by keyboard and show their tooltip", async ({
    page,
    request,
  }) => {
    const { anomalies } = await liveData(request);
    const first = anomalies.events.find((e) => e.channel === "temp");
    test.skip(!first, "No temperature event in this dataset");
    await page.goto("/anomalies");
    await settled(page);
    const timeline = page.getByRole("group", { name: "Anomaly timeline" });
    // Tab from the Run analysis button walks the page in order and reaches the first dot.
    await page.getByRole("button", { name: "Run analysis" }).focus();
    const dot = timeline.getByTestId("timeline-event").first();
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
      if (await dot.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(dot).toBeFocused();
    await expect(timeline.locator("g[aria-hidden='true']")).toContainText(
      `Cycle ${String(first?.cycle)}: ${first?.type ?? ""}`,
    );
    await page.keyboard.press("Tab");
    await expect(timeline.getByTestId("timeline-event").nth(1)).toBeFocused();
  });

  test("the limits stay collapsed until opened", async ({ page }) => {
    await page.goto("/anomalies");
    await settled(page);
    const summary = page.getByText("About these results");
    await expect(page.getByText(/slow periodic pattern/)).toBeHidden();
    await summary.click();
    await expect(page.getByText(/slow periodic pattern/)).toBeVisible();
  });
});

test.describe("Anomaly Detection on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the events table scrolls inside its card, not the page", async ({
    page,
  }) => {
    await page.goto("/anomalies");
    await settled(page);
    const scroller = page.getByLabel("Detected events table, scrolls sideways");
    const { scrollWidth, clientWidth } = await scroller.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollWidth).toBeGreaterThan(clientWidth);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBe(0);
  });
});
