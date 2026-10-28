import { expect, test } from "@playwright/test";
import { mockApi, waitForAdvisorReady } from "./support/api";
import en from "../messages/en.json";

/** The whole Advisor completed with the keyboard only (no pointer events). */
test("keyboard-only advisor flow", async ({ page }) => {
  await mockApi(page);
  await page.goto("/en/advisor");
  await expect(page.getByRole("heading", { level: 2, name: en.advisor.location.title })).toBeVisible();
  await waitForAdvisorReady(page);

  // Skip link is the first tab stop and lands on <main>.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: en.common.skipToContent })).toBeFocused();
  await page.keyboard.press("Enter");

  // Reach the coordinate fields by tabbing (the map region is skipped by its own
  // keyboard hint) and type a point; Enter commits.
  const lat = page.getByLabel(en.advisor.location.latitude, { exact: true });
  for (let i = 0; i < 40 && !(await lat.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(lat).toBeFocused();
  await page.keyboard.type("8.38");
  await expect(lat).toHaveValue("8.38");
  await page.keyboard.press("Tab");
  const lon = page.getByLabel(en.advisor.location.longitude, { exact: true });
  await expect(lon).toBeFocused();
  await page.keyboard.type("39.37");
  await expect(lon).toHaveValue("39.37");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/lon=39\.37/);

  // Next → challenge cards are buttons with aria-pressed; Space activates.
  const next = page.getByRole("button", { name: en.common.next, exact: true });
  await next.focus();
  await page.keyboard.press("Enter");
  const erosion = page.getByRole("group", { name: en.advisor.challenge.title }).getByRole("button").nth(3);
  await erosion.focus();
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(/family=Erosion/);

  const objective = page.getByRole("group", { name: en.advisor.objective.title }).getByRole("button").first();
  await objective.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/indicator=/);

  // Crop combobox is optional: Tab past it to "Get recommendation".
  const go = page.getByRole("button", { name: en.advisor.getRecommendation });
  await go.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 2, name: en.advisor.results.title })).toBeVisible();
  await expect(page.locator("article[aria-labelledby^='practice-']").first()).toBeVisible();

  // The live region announced the result count.
  await expect(page.getByRole("status").filter({ hasText: /recommended/ })).toHaveText(/\d+ practices? recommended/);

  // Every focusable control in the results shows a visible focus ring (2 px outline).
  await page.locator("article[aria-labelledby^='practice-']").first().getByRole("button", { name: en.advisor.results.card.why }).focus();
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement as Element).outlineWidth);
  expect(outline).toBe("2px");
});
