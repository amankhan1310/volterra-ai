import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import type { Scenario } from "../src/api/types";
import { liveData, settled } from "./support";

/**
 * Scenario lifecycle against the real API and database. Each test records the scenarios that
 * already exist and deletes only the ones it created, so a developer's saved scenarios survive.
 */
async function scenarioIds(request: APIRequestContext): Promise<Set<string>> {
  const { battery } = await liveData(request);
  const list = (await (
    await request.get(`/api/v1/batteries/${battery.id}/scenarios`)
  ).json()) as { items: Scenario[] };
  return new Set(list.items.map((s) => s.id));
}

let before = new Set<string>();

test.beforeEach(async ({ request }) => {
  before = await scenarioIds(request);
});

test.afterEach(async ({ request }) => {
  for (const id of await scenarioIds(request))
    if (!before.has(id)) await request.delete(`/api/v1/scenarios/${id}`);
});

const slider = (page: Page, name: RegExp) => page.getByRole("slider", { name });
const items = (page: Page) => page.getByTestId("saved-scenario");

test.describe("What-If Simulator against the real API", () => {
  test("sliders drive the simulation; Reset restores the defaults", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await page.goto("/simulator");
    await settled(page);
    await expect(page.getByTestId("cycles-to-eol")).toHaveText("106");
    await slider(page, /^Temperature/).fill("35");
    await expect(page.getByTestId("value-temp_c")).toHaveText("35 °C");
    await expect(page.getByTestId("cycles-to-eol")).toHaveText("60");
    await expect(page.getByTestId("delta")).toHaveText(
      "-46 cycles vs baseline (-43%)",
    );
    // Keyboard: one step on the charge-rate slider.
    await slider(page, /^Charge rate/).focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("value-c_rate")).toHaveText("1.1 C");
    await page.getByRole("button", { name: "Reset" }).click();
    await expect(page.getByTestId("value-temp_c")).toHaveText("25 °C");
    await expect(page.getByTestId("cycles-to-eol")).toHaveText("106");
    const canvas = await page
      .getByRole("img", { name: /^Simulated SOH over/ })
      .locator("canvas")
      .first()
      .boundingBox();
    expect(canvas?.height).toBeGreaterThan(300);
    expect(errors).toEqual([]);
  });

  test("save, rename, duplicate, delete, and scenarios persist across a reload", async ({
    page,
  }) => {
    await page.goto("/simulator");
    await settled(page);
    const start = await items(page).count();
    test.skip(start > 2, "needs room for two new scenarios (D3 limit is 4)");
    await slider(page, /^Temperature/).fill("35");
    await page.getByRole("button", { name: "Save scenario" }).click();
    const name = `Scenario ${String(start + 1)}`;
    await expect(items(page)).toHaveCount(start + 1);
    await expect(items(page).last()).toContainText(`${name} 35°C · 1C · 80%`);

    await page.getByRole("button", { name: `Rename ${name}` }).click();
    const dialog = page.getByRole("dialog", { name: "Rename scenario" });
    await expect(dialog).toBeVisible();
    const input = dialog.getByRole("textbox", { name: "Scenario name" });
    await expect(input).toBeFocused();
    await input.fill("Hot summer, fast charging every single day");
    await expect(input).toHaveValue("Hot summer, fast charging ever");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(items(page).last()).toContainText(name);

    await page.getByRole("button", { name: `Rename ${name}` }).click();
    await input.fill("Hot summer");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
    await expect(items(page).last()).toContainText("Hot summer");

    await page.getByRole("button", { name: "Duplicate Hot summer" }).click();
    await expect(items(page)).toHaveCount(start + 2);
    await expect(items(page).last()).toContainText("Hot summer copy");

    await page.reload();
    await settled(page);
    await expect(items(page)).toHaveCount(start + 2);

    await page.getByRole("button", { name: "Delete Hot summer copy" }).click();
    await expect(items(page)).toHaveCount(start + 1);
  });

  test("stops at four saved scenarios (D3)", async ({ page }) => {
    await page.goto("/simulator");
    await settled(page);
    const save = page.getByRole("button", { name: "Save scenario" });
    for (let n = await items(page).count(); n < 4; n++) {
      await save.click();
      await expect(items(page)).toHaveCount(n + 1);
    }
    await save.click();
    await expect(
      page.getByRole("status").filter({ hasText: "Delete a scenario" }),
    ).toHaveText("Delete a scenario first (max 4).");
    await expect(items(page)).toHaveCount(4);
  });

  test("EOL changed here shows the chip on the Overview (D1, U1)", async ({
    page,
  }) => {
    await page.goto("/simulator");
    await settled(page);
    await slider(page, /^End-of-life SOH/).fill("70");
    await expect(page.getByTestId("value-eol_pct")).toHaveText("70 %");
    await page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Overview" })
      .click();
    await settled(page);
    await expect(
      page.getByText("EOL threshold 70% · set in the Simulator"),
    ).toBeVisible();
    await expect(page.getByTestId("rul")).toContainText("cycles to 70% SOH");
  });
});
