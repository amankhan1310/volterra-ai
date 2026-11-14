import { expect, test, type Page } from "@playwright/test";
import { settled, startInTheme } from "./support";

/** Theme (decision D2): dark first visit, header toggle, remembered across navigation and reloads. */
const toggle = (page: Page) =>
  page.getByRole("button", { name: "Light theme" });
const html = (page: Page) => page.locator("html");

/** Computed colour of an element property, as `rgb(r, g, b)`. */
const computed = (
  page: Page,
  testId: string,
  prop: "color" | "background-color",
) =>
  page
    .getByTestId(testId)
    .first()
    .evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop);

test.describe("theme", () => {
  test("opens dark on a first visit", async ({ page }) => {
    await page.goto("/overview");
    await settled(page);
    await expect(html(page)).toHaveAttribute("data-theme", "dark");
    await expect(toggle(page)).toHaveAttribute("aria-pressed", "false");
  });

  test("the toggle switches to light, and the choice survives navigation and reload", async ({
    page,
  }) => {
    await page.goto("/overview");
    await settled(page);
    await toggle(page).click();
    await expect(html(page)).toHaveAttribute("data-theme", "light");
    await expect(toggle(page)).toHaveAttribute("aria-pressed", "true");
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Anomaly Detection" })
      .click();
    await settled(page);
    await expect(html(page)).toHaveAttribute("data-theme", "light");
    await page.reload();
    await settled(page);
    await expect(html(page)).toHaveAttribute("data-theme", "light");
    await toggle(page).click();
    await expect(html(page)).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await settled(page);
    await expect(html(page)).toHaveAttribute("data-theme", "dark");
  });

  test("a saved light theme applies before the first paint (no flash)", async ({
    page,
  }) => {
    await startInTheme(page, "light");
    await page.addInitScript(() => {
      requestAnimationFrame(() => {
        (
          window as unknown as { firstFrameTheme: string | null }
        ).firstFrameTheme = document.documentElement.getAttribute("data-theme");
      });
    });
    await page.goto("/overview");
    await settled(page);
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { firstFrameTheme: string | null })
            .firstFrameTheme,
      ),
    ).toBe("light");
  });

  test("light separates graphic and text accents; dark keeps them equal", async ({
    page,
  }) => {
    await page.goto("/advisor");
    await settled(page);
    // Dark: the bar and its Δ% text are the same green (unchanged theme).
    expect(await computed(page, "advisor-bar", "background-color")).toBe(
      "rgb(124, 242, 188)",
    );
    expect(await computed(page, "advisor-delta", "color")).toBe(
      "rgb(124, 242, 188)",
    );
    await toggle(page).click();
    // Light: the bar is the graphic green (3:1), the text the darker AA green (4.5:1).
    expect(await computed(page, "advisor-bar", "background-color")).toBe(
      "rgb(18, 137, 92)",
    );
    expect(await computed(page, "advisor-delta", "color")).toBe(
      "rgb(8, 113, 74)",
    );
  });

  test("twin modules are outlined in their tone in light only", async ({
    page,
  }) => {
    await page.goto("/digital-twin");
    await settled(page);
    const face = page
      .getByRole("button", { name: "Module 2", exact: true })
      .locator("polygon")
      .first();
    const stroke = () =>
      face.evaluate((el) => getComputedStyle(el).getPropertyValue("stroke"));
    expect(await stroke()).toBe("none");
    await toggle(page).click();
    expect(await stroke()).toBe("rgb(8, 113, 74)");
    const top = page
      .getByRole("button", { name: "Module 2", exact: true })
      .locator("polygon")
      .nth(2);
    await page.getByRole("button", { name: "Module 2", exact: true }).click();
    // Strokes animate for 0.2 s; wait for the settled outline.
    await expect
      .poll(() =>
        top.evaluate((el) => getComputedStyle(el).getPropertyValue("stroke")),
      )
      .toBe("rgb(14, 23, 38)");
  });

  test("the gauge rings use the graphic accents in light", async ({ page }) => {
    await page.goto("/overview");
    await settled(page);
    const firstStop = page
      .getByRole("img", { name: /^State of health/ })
      .locator("stop")
      .first();
    const stop = () =>
      firstStop.evaluate((el) =>
        getComputedStyle(el).getPropertyValue("stop-color"),
      );
    expect(await stop()).toBe("rgb(84, 231, 255)");
    await toggle(page).click();
    expect(await stop()).toBe("rgb(7, 147, 176)");
  });

  test("the gauge caption sits below the rings, never across them", async ({
    page,
  }) => {
    await page.goto("/overview");
    await settled(page);
    const gauge = await page
      .getByRole("img", { name: /^State of health/ })
      .boundingBox();
    const caption = await page
      .getByText(/^inner ring: life used to/)
      .boundingBox();
    expect(gauge && caption).toBeTruthy();
    if (!gauge || !caption) return;
    expect(caption.y).toBeGreaterThanOrEqual(gauge.y + gauge.height - 1);
    expect(caption.height).toBeGreaterThan(12);
  });
});
