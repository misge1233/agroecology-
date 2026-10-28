import { expect, test } from "@playwright/test";
import { RESULTS_QUERY, horizontalOverflow, mockApi } from "./support/api";

/**
 * U1 review item 0a: no screen may scroll horizontally at any of five widths.
 * `document.scrollWidth <= window.innerWidth` on every screen, in all three
 * languages for the two densest screens.
 */
const WIDTHS = [360, 390, 412, 768, 1440];
const SCREENS: { name: string; path: string }[] = [
  { name: "home", path: "/en" },
  { name: "advisor step 1", path: "/en/advisor" },
  { name: "advisor results", path: `/en/advisor?${RESULTS_QUERY}` },
  { name: "advisor results (am)", path: `/am/advisor?${RESULTS_QUERY}` },
  { name: "advisor results (om)", path: `/om/advisor?${RESULTS_QUERY}` },
  { name: "chat", path: "/en/chat" },
  { name: "chat (am)", path: "/am/chat" },
  { name: "about", path: "/en/about" },
  { name: "404", path: "/en/does-not-exist" },
];

for (const width of WIDTHS) {
  test(`no horizontal overflow at ${width}px`, async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width, height: 900 });
    for (const screen of SCREENS) {
      await page.goto(screen.path);
      await page.waitForLoadState("networkidle");
      const probe = await horizontalOverflow(page);
      expect(probe.scrollWidth, `${screen.name} @ ${width}px overflows: ${probe.offenders.join(" | ")}`).toBeLessThanOrEqual(probe.innerWidth);
      if (width === 390 && screen.name === "advisor results") {
        await page.screenshot({ path: "test-results/phone-390-results.png", fullPage: true });
      }
    }
  });
}
