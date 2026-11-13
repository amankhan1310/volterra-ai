// Milestone review screenshots: the React app and the legacy prototype, side by side.
//
//   PW_CHANNEL=msedge node scripts/review-screenshots.mjs <outDir> [reactUrl] [legacyUrl]
//
// Uses an installed browser (PW_CHANNEL, e.g. msedge or chrome) with a fresh temporary profile;
// it never downloads one. Expects the API (:8000), `npm run dev` (:5173) and the legacy prototype
// (`python -m http.server 8080 --directory legacy`) to be running.
/* global document -- used inside page.evaluate callbacks, which run in the browser */
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const [
  outDir,
  reactUrl = "http://localhost:5173",
  legacyUrl = "http://127.0.0.1:8080",
] = process.argv.slice(2);
const channel = process.env.PW_CHANNEL;
if (!outDir || !channel) {
  console.error(
    "usage: PW_CHANNEL=msedge node scripts/review-screenshots.mjs <outDir> [reactUrl] [legacyUrl]",
  );
  process.exit(2);
}

/** [React path, legacy hash key] */
const PAGES = [
  ["overview", "overview"],
  ["digital-twin", "digital"],
  ["simulator", "sim"],
  ["anomalies", "anom"],
  ["advisor", "advisor"],
  ["about", "about"],
];
const WIDTHS = [1440, 1180, 980, 860, 390];
const HEIGHT = 900;
const log = [];

const browser = await chromium.launch({ channel });

async function openReact(context, path) {
  const page = await context.newPage();
  page.on("console", (m) => {
    if (m.type() === "error")
      log.push(`react /${path}: console error: ${m.text()}`);
  });
  page.on("pageerror", (e) =>
    log.push(`react /${path}: page error: ${e.message}`),
  );
  await page.goto(`${reactUrl}/${path}`);
  await page.locator("h1").first().waitFor();
  // Wait until the page has settled on content or a state (not a loading skeleton).
  await page
    .locator(
      '[data-testid="page-placeholder"], [role="alert"], h1:has-text("Page not found")',
    )
    .first()
    .waitFor({ timeout: 15_000 });
  await page.waitForTimeout(400);
  return page;
}

async function openLegacy(context, key) {
  const page = await context.newPage();
  await page.goto(`${legacyUrl}/#${key}`);
  await page.locator("h1").first().waitFor();
  await page.waitForTimeout(1200); // ECharts entry animation
  return page;
}

async function shot(page, ...parts) {
  const file = join(outDir, ...parts);
  await page.screenshot({ path: file });
  return file;
}

for (const width of WIDTHS) {
  await mkdir(join(outDir, String(width)), { recursive: true });
  const context = await browser.newContext({
    viewport: { width, height: HEIGHT },
  });
  for (const [path, key] of PAGES) {
    const react = await openReact(context, path);
    const overflow = await react.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    if (overflow > 0)
      log.push(`react /${path} @${width}px: horizontal overflow ${overflow}px`);
    await shot(react, String(width), `react-${path}.png`);
    await react.close();
    const legacy = await openLegacy(context, key);
    await shot(legacy, String(width), `legacy-${path}.png`);
    await legacy.close();
  }
  await context.close();
}

// Interactions.
await mkdir(join(outDir, "interactions"), { recursive: true });
{
  const context = await browser.newContext({
    viewport: { width: 1440, height: HEIGHT },
  });
  const react = await openReact(context, "overview");
  await react.getByRole("button", { name: "Collapse sidebar" }).click();
  await react.waitForTimeout(400);
  await shot(react, "interactions", "react-collapsed.png");
  await react.getByRole("button", { name: "Expand sidebar" }).click();
  await react.getByRole("button", { name: /^Notifications/ }).click();
  await react.waitForTimeout(400);
  await shot(react, "interactions", "react-bell-toast.png");
  await react.getByRole("button", { name: "Run analysis" }).click();
  await react.getByText(/reloaded from the API|Reload failed/).waitFor();
  await react.waitForTimeout(300);
  await shot(react, "interactions", "react-run-analysis-toast.png");
  await react.goto(`${reactUrl}/no-such-page`);
  await react.locator("h1", { hasText: "Page not found" }).waitFor();
  await shot(react, "interactions", "react-404.png");
  await react.close();

  const legacy = await openLegacy(context, "overview");
  await legacy.locator("#cb").click();
  await legacy.waitForTimeout(400);
  await shot(legacy, "interactions", "legacy-collapsed.png");
  await legacy.locator("#cb").click();
  await legacy.locator("#bell").click();
  await legacy.waitForTimeout(400);
  await shot(legacy, "interactions", "legacy-bell-toast.png");
  await legacy.close();
  await context.close();
}
{
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const react = await openReact(context, "overview");
  await react.getByRole("button", { name: "Open menu" }).click();
  await react.waitForTimeout(400);
  await shot(react, "interactions", "react-mobile-drawer.png");
  await react.close();
  const legacy = await openLegacy(context, "overview");
  // Known prototype defect: at phone widths its overflowing header squeezes the burger button to
  // 0px wide, so it cannot be tapped. Open the drawer programmatically for the comparison.
  const burgerWidth = await legacy.evaluate(
    () => document.getElementById("bg").getBoundingClientRect().width,
  );
  if (burgerWidth === 0)
    log.push("legacy @390px: burger button is 0px wide (prototype defect)");
  await legacy.evaluate(() => document.getElementById("bg").click());
  await legacy.waitForTimeout(400);
  await shot(legacy, "interactions", "legacy-mobile-drawer.png");
  await legacy.close();
  await context.close();
}

await browser.close();
await writeFile(
  join(outDir, "review-log.txt"),
  log.length ? log.join("\n") + "\n" : "no issues\n",
);
console.log(
  log.length
    ? log.join("\n")
    : "Screenshots captured; no console errors or overflow.",
);
console.log(`Output: ${outDir}`);
