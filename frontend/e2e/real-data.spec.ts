/**
 * The real-data journey (Phase 6 M6) on the generated real-style batteries that CI imports next
 * to synthetic-v1 (backend/tests/support/fixture_bundles.py; generated values, never real data):
 * battery selection by URL, limitation states, measured data and samples, refresh and errors.
 */
import { expect, test, type Page } from "@playwright/test";
import { settled } from "./support";

const CALCE = "calce-test:CS2_T";
const NASA = "nasa-test:B0005";
const query = (key: string) => `battery=${encodeURIComponent(key)}`;

const batterySelect = (page: Page) =>
  page.getByRole("combobox", { name: "Battery", exact: true });

test("selects a measured battery, explains its limits and shows its data", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });

  // Default: the synthetic reference battery.
  await page.goto("/overview");
  await settled(page);
  await expect(page.getByLabel("Data context")).toContainText("synthetic-v1");

  // Select the CALCE-style cell: analytics refused with the API's reason.
  await batterySelect(page).selectOption(CALCE);
  await expect(page).toHaveURL(new RegExp(`/overview\\?${query(CALCE)}$`));
  await expect(
    page.getByText("Analytics are not available for CS2_T"),
  ).toBeVisible();
  await expect(page.getByTestId("limitation-message")).toContainText(
    "no temperature or voltage measurement",
  );
  await expect(page.getByLabel("Data context")).toContainText("Measured data");

  // Its measured data and samples.
  await page
    .getByTestId("limitation-message")
    .locator("..")
    .getByRole("link", { name: "Battery Data" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/battery-data\\?${query(CALCE)}$`));
  await expect(page.getByTestId("data-battery")).toHaveText("CS2_T");
  await expect(page.getByTestId("data-not-measured")).toContainText(
    "temperature",
  );
  const cycle = page.getByRole("spinbutton", { name: "Cycle number" });
  await cycle.fill("7");
  await expect(page.getByTestId("samples-note")).toHaveText(
    "Cycle 7: 1500 of 5001 measured samples (evenly downsampled for the chart; first and last kept).",
  );

  // The selection survives navigation and a full reload.
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Digital Twin" })
    .click();
  await expect(page).toHaveURL(new RegExp(`/digital-twin\\?${query(CALCE)}$`));
  await expect(
    page.getByText("This view is not available for CS2_T"),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("This view is not available for CS2_T"),
  ).toBeVisible();

  // The NASA-style cell has every measurement: the Digital Twin works on measured data.
  await batterySelect(page).selectOption(NASA);
  await settled(page);
  await expect(page.getByLabel("Data context")).toContainText("nasa-test");
  await expect(page.getByTestId("page-content")).toBeVisible();

  expect(errors).toEqual([]);
});

test("an unknown battery in the URL is reported, not replaced", async ({
  page,
}) => {
  await page.goto("/overview?battery=missing%3AX1");
  await expect(page.getByText("Battery not found")).toBeVisible();
  await expect(
    page.getByRole("group", { name: "System status" }),
  ).toContainText("Selected battery not found");
  await page.getByRole("link", { name: "default battery" }).click();
  await settled(page);
  await expect(page.getByLabel("Data context")).toContainText("synthetic-v1");
});
