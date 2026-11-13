import { defineConfig, devices } from "@playwright/test";

// CI downloads Playwright's Chromium. Locally, no browser is downloaded: set PW_CHANNEL to an
// installed browser (e.g. PW_CHANNEL=msedge) and Playwright drives it with a fresh temporary profile.
const channel = process.env["PW_CHANNEL"];
const isCI = Boolean(process.env["CI"]);
// CI serves the production build (vite preview, port 4173); locally the dev server (5173).
const baseURL =
  process.env["E2E_BASE_URL"] ??
  (isCI ? "http://localhost:4173" : "http://localhost:5173");

export default defineConfig({
  testDir: "./e2e",
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: 1,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], ...(channel ? { channel } : {}) },
    },
  ],
  webServer: {
    command: isCI ? "npm run preview" : "npm run dev",
    url: baseURL,
    reuseExistingServer: !isCI,
    timeout: 120_000,
  },
});
