import { expect, test } from "@playwright/test";
import { liveData, settled } from "./support";

test.describe("About against the real API", () => {
  test("renders the live values and limitations with no console errors", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const { battery } = await liveData(request);
    await page.goto("/about");
    await settled(page);
    await expect(page.getByTestId("about-data")).toContainText(
      `${String(battery.cycle_count)} seeded synthetic cycles of a ${battery.nominal_capacity_ah.toFixed(1)} Ah cell`,
    );
    await expect(page.getByTestId("about-method")).toContainText(
      `SOH = capacity ÷ ${String(battery.nominal_capacity_ah)} Ah`,
    );
    await expect(page.getByTestId("limitation")).toHaveCount(8);
    expect(errors).toEqual([]);
  });

  test("a limitation link opens the page that shows it", async ({ page }) => {
    await page.goto("/about");
    await settled(page);
    await page
      .getByTestId("limitation")
      .filter({ hasText: "F1" })
      .getByRole("link", { name: "Anomaly Detection" })
      .click();
    await expect(page).toHaveURL("/anomalies");
    await settled(page);
    await expect(
      page.getByRole("heading", { level: 1, name: "Anomaly Detection" }),
    ).toBeVisible();
  });

  test("defect codes appear on About only (D4)", async ({ page }) => {
    for (const path of [
      "/overview",
      "/digital-twin",
      "/simulator",
      "/anomalies",
      "/advisor",
    ]) {
      await page.goto(path);
      await settled(page);
      // Open every "About these results" so its text is checked too.
      for (const summary of await page.locator("details > summary").all())
        await summary.click();
      expect(
        await page.locator("main").innerText(),
        `defect code on ${path}`,
      ).not.toMatch(/\bF[1-8]\b/);
    }
  });
});
