import { test } from "@playwright/test";
import { RESULTS_QUERY, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";
import om from "../messages/om.json";

/**
 * U9 report screenshots (mocked API, deterministic): Home, About, Advisor
 * results and Chat at 390 and 1440 px, light and dark, in en/am/om.
 * Opt-in (SHOTS=1) because it writes 48 full-page images to
 * test-results/shots/u9/; the report copies them to docs/design/screenshots/u9/.
 */
const CATALOGS = { en, am, om } as const;
const MESSAGE = "My farm is at 8.38, 39.37 and I want to reduce erosion.";

test.skip(!process.env.SHOTS, "set SHOTS=1 to write the U9 report screenshots");

for (const locale of ["en", "am", "om"] as const) {
  for (const theme of ["light", "dark"] as const) {
    for (const width of [390, 1440] as const) {
      const height = width === 390 ? 844 : 900;
      const tag = `${locale}-${theme}-${width}`;
      test(`u9 ${tag}`, async ({ page }) => {
        test.setTimeout(120_000);
        await mockApi(page);
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        const shot = (name: string, fullPage = true) =>
          page.screenshot({ path: `test-results/shots/u9/${name}-${tag}.png`, fullPage });

        await page.goto(`/${locale}`);
        await page.waitForLoadState("networkidle");
        await shot("home");

        await page.goto(`/${locale}/about`);
        await page.waitForLoadState("networkidle");
        await shot("about");

        await page.goto(`/${locale}/advisor?${RESULTS_QUERY}`);
        await page.locator("article[aria-labelledby^='practice-']").first().waitFor();
        await page.waitForTimeout(500);
        await shot("advisor");

        const m = CATALOGS[locale];
        await page.goto(`/${locale}/chat`);
        await page.getByRole("textbox", { name: m.chat.message }).fill(MESSAGE);
        await page.getByRole("button", { name: m.chat.ask }).click();
        await page.getByTestId("chat-open-advisor").waitFor();
        await page.waitForTimeout(400);
        await shot("chat", false);
      });
    }
  }
}
