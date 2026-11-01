import { expect, test } from "@playwright/test";
import { mockApi } from "./support/api";

/**
 * U9 B1: Chrome's page translation rewrites text nodes React owns and then
 * crashes reconciliation (`NotFoundError: removeChild`, seen in the language
 * switcher's Radix SelectItemText on /am). The app ships its own en/am/om
 * copy, so every locale opts out: `<html translate="no">` plus the
 * `<meta name="google" content="notranslate">` hint.
 */
for (const locale of ["en", "am", "om"] as const) {
  test(`/${locale} opts out of browser auto-translation`, async ({ page }) => {
    await mockApi(page);
    await page.goto(`/${locale}`);
    await expect(page.locator("html[translate='no']")).toHaveCount(1);
    await expect(page.locator("head meta[name='google'][content='notranslate']")).toHaveCount(1);
  });
}
