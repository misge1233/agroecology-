import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests (U2). The production build is served by
 * `scripts/serve-standalone.mjs`; every API call is intercepted in the browser
 * (e2e/support/api.ts) so the suite needs no backend, no rasters and no
 * network. Browser: the system Chrome by default (no 150 MB download); set
 * PLAYWRIGHT_CHANNEL=chromium after `npx playwright install chromium` to use
 * the bundled build instead (CI without Chrome).
 */
const PORT = Number(process.env.E2E_PORT || 3100);
const channel = process.env.PLAYWRIGHT_CHANNEL || "chrome";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/support/**", "**/fixtures/**"],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "en-GB",
  },
  projects: [
    {
      name: "desktop",
      testIgnore: ["**/*.phone.spec.ts", "**/support/**", "**/fixtures/**"],
      use: { ...devices["Desktop Chrome"], channel, viewport: { width: 1280, height: 800 } },
    },
    {
      name: "phone",
      testMatch: ["**/*.phone.spec.ts"],
      use: { ...devices["Pixel 7"], channel },
    },
  ],
  webServer: {
    command: "node scripts/serve-standalone.mjs",
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
    env: { PORT: String(PORT), HOSTNAME: "127.0.0.1" },
  },
});
