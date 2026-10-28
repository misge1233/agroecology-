import { expect, test } from "@playwright/test";
import { RESULTS_QUERY, mockApi } from "./support/api";
import en from "../messages/en.json";

/** Phone project (Pixel 7 emulation): deferred map, tile failure, overflow. */
test("the map is deferred on phones until requested; inputs work without it", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto("/en/advisor");
  await expect(page.getByRole("button", { name: en.advisor.location.showMap })).toBeVisible();
  await expect(page.locator(".leaflet-container")).toHaveCount(0);
  // Coordinates work without the map.
  await page.getByLabel(en.advisor.location.latitude, { exact: true }).fill("8.38");
  await page.getByLabel(en.advisor.location.longitude, { exact: true }).fill("39.37");
  await page.getByLabel(en.advisor.location.longitude, { exact: true }).press("Enter");
  await expect(page).toHaveURL(/lat=8\.38/);
  await expect.poll(() => calls.some((c) => c.url.startsWith("/context")), { timeout: 10_000 }).toBe(true);
  // A pin exists now, so the map shows; otherwise "Show the map" mounts it.
  await expect(page.locator(".leaflet-container")).toBeVisible();
});

test("tile failure shows a message and keeps the coordinate inputs usable", async ({ page }) => {
  await mockApi(page, { tilesFail: true });
  await page.goto("/en/advisor");
  await page.getByRole("button", { name: en.advisor.location.showMap }).click();
  await expect(page.getByRole("alert").filter({ hasText: en.advisor.location.tilesFailed })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel(en.advisor.location.latitude, { exact: true }).fill("9.03");
  await page.getByLabel(en.advisor.location.longitude, { exact: true }).fill("38.74");
  await page.getByLabel(en.advisor.location.longitude, { exact: true }).press("Enter");
  await expect(page).toHaveURL(/lat=9\.03/);
});

test("results fit a 390 px phone with the bottom tab bar", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.locator("article[aria-labelledby^='practice-']").first()).toBeVisible();
  const probe = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(probe.sw).toBeLessThanOrEqual(probe.iw);
  await expect(page.getByRole("navigation", { name: en.nav.bottom })).toBeVisible();
});
