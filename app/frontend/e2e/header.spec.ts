import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "./support/api";

/**
 * U9 B2: the sticky header must stay (near-)opaque over every section. The
 * colour tokens are RGB channels consumed as `rgb(var(--x) / <alpha-value>)`;
 * before that, `bg-surface/90` compiled to nothing and the header was
 * transparent over the hero photo and the CTA band.
 */
const MIN_ALPHA = 0.85;

/** Alpha of the site header's computed background colour (0 when transparent). */
async function headerAlpha(page: Page): Promise<number> {
  const bg = await page.getByRole("banner").evaluate((el) => getComputedStyle(el).backgroundColor);
  if (bg === "transparent") return 0;
  // Chrome serialises as rgb(r, g, b) / rgba(r, g, b, a); tolerate the
  // space-separated "/ a" and color(srgb ...) forms too.
  const nums = bg.match(/[\d.]+%?/g) ?? [];
  if (nums.length < 4) return 1;
  const a = nums[3];
  return a.endsWith("%") ? parseFloat(a) / 100 : parseFloat(a);
}

async function expectOpaqueHeader(page: Page, where: string) {
  const alpha = await headerAlpha(page);
  expect(alpha, `header background alpha ${where}`).toBeGreaterThanOrEqual(MIN_ALPHA);
}

async function scrollToCta(page: Page) {
  await page.locator("#cta-title").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -80));
  await expect(page.getByRole("banner")).toBeInViewport();
}

test.describe("sticky header is opaque (desktop)", () => {
  test("over the hero at the top of /en", async ({ page }) => {
    await mockApi(page);
    await page.goto("/en");
    await expectOpaqueHeader(page, "over the hero");
  });

  test("over the CTA band near the bottom of /en", async ({ page }) => {
    await mockApi(page);
    await page.goto("/en");
    await scrollToCta(page);
    await expectOpaqueHeader(page, "over the CTA band");
  });
});

test.describe("sticky header is opaque (390 px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("over the hero and the CTA band of /en", async ({ page }) => {
    await mockApi(page);
    await page.goto("/en");
    await expectOpaqueHeader(page, "over the hero @390");
    await scrollToCta(page);
    await expectOpaqueHeader(page, "over the CTA band @390");
  });
});
