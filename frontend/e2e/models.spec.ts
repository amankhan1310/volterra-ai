/**
 * Phase 7 models against the real API, on the generated model run that CI imports with the
 * generated bundles (tests/support/model_runs.py: made-up values, never a real result).
 */
import { expect, test } from "@playwright/test";
import { settled } from "./support";

test("the Models page shows the run, CV vs held-out test and its limits", async ({
  page,
}) => {
  await page.goto("/models");
  await settled(page);
  await expect(page.getByTestId("run-id")).toHaveText("generated0001");
  await expect(page.getByText("Experimental", { exact: true })).toBeVisible();
  await expect(page.getByTestId("how-to-read")).toContainText(
    "Cross-validation: out-of-fold errors",
  );
  const rul = page.getByTestId("task-rul");
  await expect(
    rul.getByRole("columnheader", { name: "Held-out test MAE" }),
  ).toBeVisible();
  await expect(
    rul.getByRole("row", { name: /^lightgbm \(selected\)/ }).first(),
  ).toBeVisible();
  await expect(rul.getByTestId("small-test-warning")).toBeVisible();
});

test("Battery Data shows a held-out battery's RUL prediction with its interval", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto("/battery-data?battery=calce-test%3ACS2_T");
  const panel = page.getByTestId("rul-panel");
  await expect(panel.getByTestId("rul-warning")).toContainText(
    "not production-validated",
  );
  await expect(panel.getByTestId("rul-latest")).toContainText("90% interval");
  await expect(panel.getByTestId("rul-split")).toContainText(
    "Held-out test battery",
  );
  await panel.getByRole("link", { name: "Models" }).click();
  await expect(page).toHaveURL(/\/models\?battery=calce-test%3ACS2_T$/);
  await page.goto("/battery-data");
  await expect(page.getByTestId("rul-none")).toContainText(
    "synthetic reference battery",
  );
  expect(errors).toEqual([]);
});

test("the Digital Twin shows the experimental RUL for a real battery", async ({
  page,
}) => {
  await page.goto("/digital-twin?battery=nasa-test%3AB0005");
  await settled(page);
  const panel = page.getByTestId("rul-panel");
  await expect(panel.getByTestId("rul-warning")).toBeVisible();
  await expect(panel.getByTestId("rul-split")).toContainText("in-sample");
});

test("the simulator shows the evidence behind its assumptions", async ({
  page,
}) => {
  await page.goto("/simulator");
  await settled(page);
  const card = page.getByTestId("simulator-evidence");
  await expect(card.getByTestId("evidence-temperature")).toContainText(
    "not a calibration",
  );
  await expect(card.getByTestId("baseline-validation")).toBeVisible();
});
