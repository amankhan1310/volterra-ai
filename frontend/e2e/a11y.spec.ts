import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { PAGES, settled } from "./support";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/** Serious and critical axe violations (the approved Definition of Done threshold). */
async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      targets: v.nodes.map((n) => n.target.join(" ")),
    }));
}

test.describe("accessibility (axe, WCAG 2.1 A/AA)", () => {
  for (const target of PAGES) {
    test(`${target.label} has no serious or critical violations`, async ({
      page,
    }) => {
      await page.goto(target.path);
      await settled(page);
      expect(await seriousViolations(page)).toEqual([]);
    });
  }

  test("404 page", async ({ page }) => {
    await page.goto("/nowhere");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Page not found",
    );
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("collapsed sidebar", async ({ page }) => {
    await page.goto("/overview");
    await settled(page);
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("mobile drawer open", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/overview");
    await settled(page);
    await page.getByRole("button", { name: "Open menu" }).click();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("keyboard: skip link, then the navigation", async ({ page }) => {
    await page.goto("/overview");
    await settled(page);
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Skip to content" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "About" })
      .focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL("/about");
  });
});
