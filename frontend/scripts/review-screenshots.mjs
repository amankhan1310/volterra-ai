// Milestone review screenshots: the React app and the legacy prototype, side by side.
//
//   PW_CHANNEL=msedge node scripts/review-screenshots.mjs <outDir> [reactUrl] [legacyUrl]
//
// Uses an installed browser (PW_CHANNEL, e.g. msedge or chrome) with a fresh temporary profile;
// it never downloads one. Expects the API (:8000), `npm run dev` (:5173) and the legacy prototype
// (`python -m http.server 8080 --directory legacy`) to be running.
/* global document, Event, MouseEvent -- used inside page.evaluate callbacks, which run in the browser */
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
  // Wait until the page has settled on content or a state, with no loading skeleton left.
  await page
    .locator(
      '[data-testid="page-content"], [data-testid="page-placeholder"], [role="alert"], h1:has-text("Page not found")',
    )
    .first()
    .waitFor({ timeout: 15_000 });
  await page
    .locator('[role="status"][aria-label^="Loading"]')
    .first()
    .waitFor({ state: "detached", timeout: 15_000 });
  await page.waitForTimeout(1200); // gauge and ECharts entry animations
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

// Full-length Overview (a tall viewport, because both apps scroll inside <main>).
await mkdir(join(outDir, "full"), { recursive: true });
for (const [width, height] of [
  [1440, 2300],
  [390, 6200],
]) {
  const context = await browser.newContext({ viewport: { width, height } });
  const react = await openReact(context, "overview");
  await shot(react, "full", `react-overview-${width}.png`);
  await react.close();
  const legacy = await openLegacy(context, "overview");
  await shot(legacy, "full", `legacy-overview-${width}.png`);
  await legacy.close();
  await context.close();
}

// Overview interactions, React and legacy in the same state.
await mkdir(join(outDir, "overview"), { recursive: true });
{
  const context = await browser.newContext({
    viewport: { width: 1440, height: 2300 },
  });
  const react = await openReact(context, "overview");
  const legacy = await openLegacy(context, "overview");
  await react
    .getByRole("group", { name: "Timeline range" })
    .getByRole("button", { name: "Last 120" })
    .click();
  await legacy.locator('#rg button[data-r="120"]').click();
  await react
    .getByRole("group", { name: "Telemetry channel" })
    .getByRole("button", { name: "Voltage" })
    .click();
  await legacy.locator('#tsel button[data-m="volt"]').click();
  await react.waitForTimeout(1000);
  await legacy.waitForTimeout(1000);
  await shot(react, "overview", "react-last120-voltage.png");
  await shot(legacy, "overview", "legacy-last120-voltage.png");
  for (const [page, selector] of [
    [react, '[role="img"][aria-label^="SOH over"]'],
    [legacy, "#tl"],
  ]) {
    const box = await page.locator(selector).boundingBox();
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.45);
  }
  await react.waitForTimeout(500);
  await legacy.waitForTimeout(500);
  await shot(react, "overview", "react-timeline-tooltip.png");
  await shot(legacy, "overview", "legacy-timeline-tooltip.png");
  await react.getByText("95% fit interval").hover();
  await react.waitForTimeout(300);
  await shot(react, "overview", "react-infotip.png");
  await react.getByText("About these results").click();
  await react.waitForTimeout(300);
  await shot(react, "overview", "react-about-these-results.png");
  await react.close();
  await legacy.close();
  await context.close();
}

// Digital Twin interactions: cycle 170 in Temperature mode with module 9 lifted, both apps.
await mkdir(join(outDir, "twin"), { recursive: true });
for (const [width, height] of [
  [1440, HEIGHT],
  [390, 1700],
]) {
  const context = await browser.newContext({ viewport: { width, height } });
  const react = await openReact(context, "digital-twin");
  await react.getByRole("slider", { name: /Cycle/ }).fill("170");
  await react
    .getByRole("group", { name: "Colour modules by" })
    .getByRole("button", { name: "Temperature" })
    .click();
  await react.getByRole("button", { name: "Module 9" }).click();
  await react.getByText("Pack state at cycle 170").waitFor();
  await react.waitForTimeout(700);
  await shot(react, "twin", `react-170-temp-module9-${width}.png`);
  await react.close();
  const legacy = await openLegacy(context, "digital");
  await legacy.evaluate(() => {
    const slider = document.getElementById("cs");
    slider.value = "170";
    slider.dispatchEvent(new Event("input"));
    document.querySelector('#sg button[data-m="temp"]').click();
    document
      .querySelector('#pack .mod[data-k="8"]')
      .dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await legacy.waitForTimeout(700);
  await shot(legacy, "twin", `legacy-170-temp-module9-${width}.png`);
  await legacy.close();
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
