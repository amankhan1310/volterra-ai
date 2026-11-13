import { expect, test } from "@playwright/test";
import type { Summary } from "../src/api/types";
import { liveData, settled } from "./support";

async function liveSummary(
  request: Parameters<typeof liveData>[0],
): Promise<Summary> {
  const { battery } = await liveData(request);
  const response = await request.get(
    `/api/v1/batteries/${battery.id}/summary?eol_pct=80`,
  );
  return (await response.json()) as Summary;
}

test.describe("Overview against the real API", () => {
  test("renders the live results with no console errors", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const summary = await liveSummary(request);
    await page.goto("/overview");
    await settled(page);
    const soh = (summary.soh_now.value ?? NaN).toFixed(1);
    await expect(
      page.getByRole("img", { name: `State of health ${soh} percent` }),
    ).toBeVisible();
    await expect(page.getByTestId("condition")).toHaveText(summary.condition);
    await expect(page.getByTestId("rul")).toHaveText(
      `${String(Math.round(summary.rul.point ?? NaN))}cycles to 80% SOH`,
    );
    await expect(page.getByTestId("kpi-value")).toHaveCount(6);
    await expect(page.getByTestId("insight-text")).toHaveCount(4);
    // Both charts drew onto a real canvas.
    for (const name of [/^SOH over /, /^Temperature per cycle/]) {
      const box = await page
        .getByRole("img", { name })
        .locator("canvas")
        .first()
        .boundingBox();
      expect(box?.width).toBeGreaterThan(200);
      expect(box?.height).toBeGreaterThan(200);
    }
    expect(errors).toEqual([]);
  });

  test("range toggle, channel switch, tooltip and the limits section work", async ({
    page,
  }) => {
    await page.goto("/overview");
    await settled(page);
    const range = page.getByRole("group", { name: "Timeline range" });
    await range.getByRole("button", { name: "Last 120" }).click();
    await expect(
      range.getByRole("button", { name: "Last 120" }),
    ).toHaveAttribute("aria-pressed", "true");
    await range.getByRole("button", { name: "Full" }).click();
    await expect(range.getByRole("button", { name: "Full" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    const channels = page.getByRole("group", { name: "Telemetry channel" });
    for (const [label, flagged] of [
      ["Voltage", 2],
      ["SOH", 5],
      ["Capacity", 0],
      ["Temperature", 1],
    ] as const) {
      await channels.getByRole("button", { name: label }).click();
      await expect(
        page.getByRole("img", {
          name: `${label} per cycle, ${String(flagged)} flagged points.`,
        }),
      ).toBeVisible();
    }

    const timeline = page.getByRole("img", { name: /^SOH over / });
    const box = await timeline.boundingBox();
    if (!box) throw new Error("timeline not laid out");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await expect(page.getByText(/^Cycle \d+/).first()).toBeVisible();

    await page.getByText("About these results").click();
    await expect(page.getByText(/backtest error of/)).toBeVisible();
  });

  test("Run analysis reloads and quotes SOH and RUL", async ({
    page,
    request,
  }) => {
    const summary = await liveSummary(request);
    await page.goto("/overview");
    await settled(page);
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "reloaded" }),
    ).toHaveText(
      `Analysis results reloaded from the API (synthetic-v1, algorithm v1): SOH ${(summary.soh_now.value ?? NaN).toFixed(1)}%, RUL ${String(Math.round(summary.rul.point ?? NaN))} cycles. No model was retrained.`,
    );
  });

  test("a failing card shows its own error and the rest of the page stays", async ({
    page,
  }) => {
    await page.route("**/api/v1/batteries/*/insights", (route) =>
      route.fulfill({
        status: 503,
        json: {
          error: {
            code: "database_unavailable",
            message: "The database is not configured",
            details: null,
          },
        },
      }),
    );
    await page.goto("/overview");
    await expect(page.getByRole("alert")).toContainText("Database unavailable");
    await expect(page.getByTestId("page-content")).toBeVisible();
    await expect(page.getByTestId("kpi-value")).toHaveCount(6);
  });
});
