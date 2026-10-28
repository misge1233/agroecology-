import { test } from "@playwright/test";
import { RESULTS_QUERY, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";
import om from "../messages/om.json";

/**
 * Documentation screenshots for the phase report (mocked API, deterministic):
 * the chat after a scored answer in the three languages, light and dark.
 * Written to test-results/shots/; the report copies them to docs/design/screenshots.
 */
const CATALOGS = { en, am, om } as const;
const MESSAGE = "My farm is at 8.38, 39.37 and I want to reduce erosion.";

for (const [locale, theme, width, height] of [
  ["en", "light", 1280, 900],
  ["am", "dark", 390, 844],
  ["om", "light", 390, 844],
] as const) {
  test(`chat screenshot ${locale} ${theme}`, async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: theme });
    await page.goto(`/${locale}/chat`);
    const m = CATALOGS[locale];
    await page.getByRole("textbox", { name: m.chat.message }).fill(MESSAGE);
    await page.getByRole("button", { name: m.chat.ask }).click();
    await page.getByTestId("chat-recommendation").waitFor();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `test-results/shots/chat-${locale}-${theme}-${width}.png`, fullPage: width > 500 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `test-results/shots/chat-${locale}-${theme}-${width}-top.png`, fullPage: false });
  });
}

test("advisor results phone 390 light (0a proof)", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await page.locator("article[aria-labelledby^='practice-']").first().waitFor();
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/shots/advisor-results-en-light-390.png", fullPage: true });
});
