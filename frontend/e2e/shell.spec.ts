import { expect, test } from "@playwright/test";
import { PAGES, liveData, settled } from "./support";

test.describe("application shell against the real API", () => {
  test("shows live API state in the header, sidebar and context bar", async ({
    page,
    request,
  }) => {
    const { battery, anomalies } = await liveData(request);
    await page.goto("/overview");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Battery Intelligence",
    );
    await expect(
      page.getByText(
        `Simulated · ${battery.nominal_capacity_ah.toFixed(1)} Ah cell profile`,
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: `Notifications: ${anomalies.summary.total} anomaly events flagged`,
      }),
    ).toBeVisible();
    const status = page.getByRole("group", { name: "System status" });
    await expect(status).toContainText("Simulation mode");
    await expect(status).toContainText("API and database online");
    const context = page.getByLabel("Data context");
    await expect(context).toContainText(`Dataset ${battery.dataset}`);
    await expect(context).toContainText(`Battery ${battery.external_id}`);
    await expect(context).toContainText("Algorithm v1");
    await expect(page.getByTestId("page-content")).toBeVisible();
  });

  for (const target of PAGES) {
    test(`navigates to ${target.label} from the sidebar`, async ({ page }) => {
      const errors: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text());
      });
      await page.goto(target.key === "overview" ? "/about" : "/overview");
      await page
        .getByRole("navigation", { name: "Main" })
        .getByRole("link", { name: target.label })
        .click();
      await expect(page).toHaveURL(target.path);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        target.title,
      );
      await expect(page.getByText(target.subtitle)).toBeVisible();
      await expect(
        page
          .getByRole("navigation", { name: "Main" })
          .getByRole("link", { name: target.label }),
      ).toHaveAttribute("aria-current", "page");
      await expect(page).toHaveTitle(`${target.label} · VOLTERRA AI`);
      await settled(page);
      await expect(page.getByTestId("page-content")).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test("redirects legacy hash bookmarks", async ({ page }) => {
    await page.goto("/#anom");
    await expect(page).toHaveURL("/anomalies");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Anomaly Detection",
    );
  });

  test("quick navigation changes page", async ({ page }) => {
    await page.goto("/overview");
    await page
      .getByRole("combobox", { name: "Quick navigation" })
      .selectOption({ label: "What-If Simulator" });
    await expect(page).toHaveURL("/simulator");
    await expect(
      page.getByRole("navigation", { name: "Breadcrumb" }),
    ).toContainText("What-If Simulator");
  });

  test("unknown paths show the 404 page", async ({ page }) => {
    await page.goto("/does-not-exist");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Page not found",
    );
    await page
      .getByRole("main")
      .getByRole("link", { name: "Overview" })
      .click();
    await expect(page).toHaveURL("/overview");
  });

  test("the sidebar collapses to icons and expands", async ({ page }) => {
    await page.goto("/overview");
    const sidebar = page.getByRole("complementary", { name: "Sidebar" });
    const wide = (await sidebar.boundingBox())?.width ?? 0;
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
    await expect
      .poll(async () => (await sidebar.boundingBox())?.width)
      .toBe(72);
    await expect(
      page.getByRole("group", { name: "System status" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Expand sidebar" }).click();
    await expect
      .poll(async () => (await sidebar.boundingBox())?.width)
      .toBe(wide);
  });

  test("the bell and Run analysis report through the toast", async ({
    page,
    request,
  }) => {
    const { anomalies } = await liveData(request);
    await page.goto("/overview");
    await settled(page);
    await page.getByRole("button", { name: /^Notifications: / }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "anomaly events" }),
    ).toHaveText(
      `${anomalies.summary.total} anomaly events flagged in the dataset. Open Anomaly Detection to review.`,
    );
    // Pages other than Overview report the reload only; Overview adds SOH and RUL (overview.spec.ts).
    await page.goto("/about");
    await settled(page);
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "reloaded" }),
    ).toHaveText(
      "Analysis results reloaded from the API (synthetic-v1, algorithm v1). No model was retrained.",
    );
  });
});

test.describe("failure states", () => {
  test("an unreachable API is explained, and recovers on retry", async ({
    page,
  }) => {
    let down = true;
    await page.route("**/api/v1/**", async (route) => {
      if (down) await route.abort("connectionrefused");
      else await route.continue();
    });
    await page.goto("/overview");
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("API unreachable");
    await expect(alert).toContainText("uvicorn");
    await expect(
      page.getByRole("group", { name: "System status" }),
    ).toContainText("API unreachable");
    down = false;
    await alert.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("page-content")).toBeVisible();
  });

  test("an empty database explains how to seed it", async ({ page }) => {
    await page.route("**/api/v1/batteries", (route) =>
      route.fulfill({ json: { items: [] } }),
    );
    await page.goto("/overview");
    await expect(page.getByText("No battery data")).toBeVisible();
    await expect(
      page.getByText("cd backend && uv run python -m app.db.seed"),
    ).toBeVisible();
  });
});
