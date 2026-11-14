import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import type { Advisor } from "../src/api/types";
import { liveData, settled } from "./support";

async function liveAdvisor(
  request: APIRequestContext,
  eol: number,
  start: number,
): Promise<Advisor> {
  const { battery } = await liveData(request);
  const response = await request.get(
    `/api/v1/batteries/${battery.id}/advisor?eol_pct=${String(eol)}&start_soh_pct=${String(start)}`,
  );
  return (await response.json()) as Advisor;
}

const cycles = (n: number | null) => (n === null ? ">5000" : String(n));

/** Sets EOL and initial SOH on the Simulator, then opens the Advisor in-app (shared draft, D1). */
async function fromSimulator(page: Page, eol: number, start: number) {
  await page.goto("/simulator");
  await settled(page);
  await page.getByRole("slider", { name: /^Initial SOH/ }).fill(String(start));
  await page
    .getByRole("slider", { name: /^End-of-life SOH/ })
    .fill(String(eol));
  await expect(page.getByTestId("value-eol_pct")).toHaveText(
    `${String(eol)} %`,
  );
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Charging Advisor" })
    .click();
  await settled(page);
}

async function expectRows(page: Page, advisor: Advisor) {
  const rows = page.getByTestId("advisor-row");
  await expect(rows).toHaveCount(advisor.rows.length);
  for (const [i, row] of advisor.rows.entries()) {
    await expect(rows.nth(i)).toContainText(row.change);
    await expect(rows.nth(i).getByTestId("advisor-cycles")).toHaveText(
      cycles(row.cycles_to_eol),
    );
  }
}

test.describe("Charging Advisor against the real API", () => {
  test("renders the live baseline and rows at the defaults, with no console errors", async ({
    page,
    request,
  }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    const advisor = await liveAdvisor(request, 80, 86.1);
    await page.goto("/advisor");
    await settled(page);
    await expect(page.getByTestId("advisor-baseline")).toHaveText(
      `${cycles(advisor.baseline_cycles_to_eol)}cycles to 80% SOH`,
    );
    await expectRows(page, advisor);
    await expect(page.getByText(/set in the Simulator/)).toHaveCount(0);
    await expect(page.getByTestId("advisor-baseline-notice")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("EOL and initial SOH set in the Simulator reach the Advisor with chips (D1, U1)", async ({
    page,
    request,
  }) => {
    const advisor = await liveAdvisor(request, 70, 90);
    await fromSimulator(page, 70, 90);
    await expect(page.getByTestId("advisor-baseline-label")).toHaveText(
      "Baseline · 25 °C · 1C · 80% DoD from 90% SOH",
    );
    await expect(page.getByTestId("advisor-baseline")).toHaveText(
      `${cycles(advisor.baseline_cycles_to_eol)}cycles to 70% SOH`,
    );
    await expectRows(page, advisor);
    await expect(
      page.getByText("EOL threshold 70% · set in the Simulator"),
    ).toBeVisible();
    await expect(
      page.getByText("Initial SOH 90% · set in the Simulator"),
    ).toBeVisible();
    // The shared draft is not persisted: a reload returns to the API defaults.
    await page.reload();
    await settled(page);
    await expect(page.getByText(/set in the Simulator/)).toHaveCount(0);
    await expect(page.getByTestId("advisor-baseline")).toContainText(
      "cycles to 80% SOH",
    );
  });

  test("an initial SOH already at end of life is explained once, on the baseline", async ({
    page,
  }) => {
    await fromSimulator(page, 90, 85);
    await expect(page.getByTestId("advisor-baseline-notice")).toHaveText(
      "Already at end of life · every change shown as 0%",
    );
    await expect(page.getByTestId("advisor-row-notice")).toHaveCount(0);
    await expect(page.getByTestId("advisor-delta")).toHaveText(
      Array.from({ length: 6 }, () => "0%"),
    );
  });
});

test.describe("Charging Advisor on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("each row stacks: label, bar, value", async ({ page }) => {
    await page.goto("/advisor");
    await settled(page);
    const row = page.getByTestId("advisor-row").first();
    const label = await row.locator("b").first().boundingBox();
    const bar = await row.getByRole("img").boundingBox();
    const value = await row.getByTestId("advisor-cycles").boundingBox();
    expect(label && bar && value).toBeTruthy();
    if (!label || !bar || !value) return;
    expect(bar.y).toBeGreaterThan(label.y);
    expect(value.y).toBeGreaterThan(bar.y);
    expect(bar.width).toBeGreaterThan(300);
  });
});
