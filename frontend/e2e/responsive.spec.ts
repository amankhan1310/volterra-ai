import { expect, test } from "@playwright/test";
import {
  PAGES,
  horizontalOverflow,
  oversizedHidden,
  settled,
  startInTheme,
  verticalOverflow,
  type Theme,
} from "./support";

// The approved review widths: desktop, the legacy breakpoints (1180, 980, 860) and a phone.
const WIDTHS = [1440, 1180, 980, 860, 390];

for (const width of WIDTHS) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    for (const theme of ["dark", "light"] as Theme[])
      test(`no page scrolls horizontally (${theme})`, async ({ page }) => {
        await startInTheme(page, theme);
        for (const target of PAGES) {
          await page.goto(target.path);
          await settled(page);
          expect(
            await horizontalOverflow(page),
            `${target.path} @${width}px`,
          ).toBe(0);
          expect(
            await oversizedHidden(page),
            `hidden content laid out on ${target.path} @${width}px`,
          ).toEqual([]);
          expect(
            await verticalOverflow(page),
            `document scrolls on ${target.path} @${width}px`,
          ).toBe(0);
        }
      });

    if (width <= 860) {
      test("the sidebar is an off-canvas drawer", async ({ page }) => {
        await page.goto("/overview");
        const sidebar = page.getByRole("complementary", {
          name: "Sidebar",
          includeHidden: true,
        });
        await expect(
          page.getByRole("button", { name: "Collapse sidebar" }),
        ).toBeHidden();
        await expect
          .poll(async () => (await sidebar.boundingBox())?.x ?? 0)
          .toBeLessThan(0);
        await page.getByRole("button", { name: "Open menu" }).click();
        await expect.poll(async () => (await sidebar.boundingBox())?.x).toBe(0);
        await sidebar.getByRole("link", { name: "Charging Advisor" }).click();
        await expect(page).toHaveURL("/advisor");
        await expect
          .poll(async () => (await sidebar.boundingBox())?.x ?? 0)
          .toBeLessThan(0);
        expect(await horizontalOverflow(page)).toBe(0);
      });
    } else {
      test("the sidebar is docked with a collapse button", async ({ page }) => {
        await page.goto("/overview");
        await expect(
          page.getByRole("button", { name: "Open menu" }),
        ).toBeHidden();
        await expect(
          page.getByRole("button", { name: "Collapse sidebar" }),
        ).toBeVisible();
        await expect(
          page.getByRole("complementary", { name: "Sidebar" }),
        ).toBeInViewport();
      });
    }
  });
}
