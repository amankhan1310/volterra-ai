import { expect, test, type Page } from "@playwright/test";
import type { Twin } from "../src/api/types";
import { liveData, settled } from "./support";

const panel = (page: Page) => page.getByTestId("page-content");

async function liveTwin(
  request: Parameters<typeof liveData>[0],
  cycle: number,
): Promise<Twin> {
  const { battery } = await liveData(request);
  return (await (
    await request.get(
      `/api/v1/batteries/${battery.id}/twin?cycle=${String(cycle)}`,
    )
  ).json()) as Twin;
}

test.describe("Digital Twin against the real API", () => {
  test("shows the latest cycle and follows the slider", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await page.goto("/digital-twin");
    await settled(page);
    const latest = await liveTwin(request, 319);
    await expect(panel(page)).toContainText(
      `Pack state at cycle ${String(latest.cycle)}`,
    );
    await expect(page.getByTestId("pack-stats")).toContainText(
      `${(latest.pack.soh.value ?? NaN).toFixed(1)}%`,
    );

    const slider = page.getByRole("slider", { name: /Cycle/ });
    await slider.fill("160");
    await expect(page.getByTestId("cycle-value")).toHaveText("160");
    const mid = await liveTwin(request, 160);
    await expect(panel(page)).toContainText("Pack state at cycle 160");
    await expect(page.getByTestId("pack-stats")).toContainText(
      `${(mid.pack.capacity.value ?? NaN).toFixed(3)}Ah`,
    );
    // Keyboard on the slider moves one cycle.
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    await expect(panel(page)).toContainText("Pack state at cycle 161");
    expect(errors).toEqual([]);
  });

  test("modes, module selection (mouse and keyboard) and reset", async ({
    page,
  }) => {
    await page.goto("/digital-twin");
    await settled(page);
    await page.getByRole("slider", { name: /Cycle/ }).fill("170");
    await expect(panel(page)).toContainText("Pack state at cycle 170");
    await page
      .getByRole("group", { name: "Colour modules by" })
      .getByRole("button", { name: "Temperature" })
      .click();
    const first = page.getByRole("button", { name: "Module 1" });
    await expect(first.locator("polygon").nth(2)).toHaveAttribute(
      "fill",
      "var(--am)",
    );

    await page.getByRole("button", { name: "Module 4" }).click();
    await expect(page.getByTestId("module-message")).toContainText("Module 4:");
    await page.getByRole("button", { name: "Module 9" }).focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("button", { name: "Module 9" }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Module 10" }).focus();
    await page.keyboard.press(" ");
    await expect(page.getByTestId("module-message")).toContainText(
      "Module 10:",
    );

    await page.getByRole("button", { name: "Reset view" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "View reset" }),
    ).toHaveText("View reset to the latest cycle");
    await expect(panel(page)).toContainText("Pack state at cycle 319");
    await expect(page.getByTestId("module-message")).toHaveText(
      "No module selected.",
    );
  });

  test("an out-of-range response keeps the last good state", async ({
    page,
  }) => {
    await page.goto("/digital-twin");
    await settled(page);
    await page.route("**/api/v1/batteries/*/twin?cycle=200", (route) =>
      route.fulfill({
        status: 422,
        json: {
          error: {
            code: "cycle_out_of_range",
            message: "Cycle 200 not found",
            details: null,
          },
        },
      }),
    );
    await page.getByRole("slider", { name: /Cycle/ }).fill("200");
    await expect(page.getByRole("alert")).toContainText(
      "Could not load cycle 200 (Cycle 200 not found). Showing cycle 319.",
    );
    await expect(panel(page)).toContainText("Pack state at cycle 319");
  });
});
