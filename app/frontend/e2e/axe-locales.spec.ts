import { expect, test, type Page } from "@playwright/test";
import { axe } from "./support/axe";
import { RESULTS_QUERY, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";
import om from "../messages/om.json";

/**
 * U9 acceptance: axe (WCAG 2 A/AA, contrast included) on every locale and
 * both themes, over the pages U9 changed: Home, About, the fused Advisor
 * results and an answered chat.
 */
const CATALOGS = { en, am, om } as const;

async function scan(page: Page, label: string) {
  await page.waitForLoadState("networkidle");
  const results = await axe(page).disableRules(["color-contrast"]).analyze();
  expect(results.violations, `${label}: ${JSON.stringify(results.violations.map((v) => [v.id, v.nodes.length, v.nodes[0]?.html]))}`).toEqual([]);
  const contrast = await axe(page).withRules(["color-contrast"]).analyze();
  expect(contrast.violations.flatMap((v) => v.nodes.map((n) => n.html)), `${label} contrast`).toEqual([]);
}

for (const locale of ["en", "am", "om"] as const) {
  for (const theme of ["light", "dark"] as const) {
    test(`axe ${locale} ${theme}: home, about, results, chat`, async ({ page }) => {
      test.setTimeout(180_000);
      await mockApi(page);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.goto(`/${locale}`);
      await scan(page, `/${locale} ${theme}`);
      await page.goto(`/${locale}/about`);
      await scan(page, `/${locale}/about ${theme}`);
      await page.goto(`/${locale}/advisor?${RESULTS_QUERY}`);
      await page.locator("article[aria-labelledby^='practice-']").first().waitFor();
      await scan(page, `/${locale}/advisor results ${theme}`);
      const m = CATALOGS[locale];
      await page.goto(`/${locale}/chat`);
      await page.getByRole("textbox", { name: m.chat.message }).fill("My farm is at 8.38, 39.37 and I want to reduce erosion.");
      await page.getByRole("button", { name: m.chat.ask }).click();
      await page.getByTestId("chat-open-advisor").waitFor();
      await scan(page, `/${locale}/chat ${theme}`);
    });
  }
}
