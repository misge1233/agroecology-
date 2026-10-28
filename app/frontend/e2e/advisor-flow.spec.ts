import { expect, test } from "@playwright/test";
import { RESULTS_QUERY, mockApi, waitForAdvisorReady } from "./support/api";
import { axe } from "./support/axe";
import { indicatorLabel } from "../src/i18n/glossary";

/**
 * The Advisor flow end to end in the three languages, with the API mocked.
 * Selectors are roles and catalog text (read from messages/*.json) so the
 * same test runs in en/am/om without hard-coded translations.
 */
import en from "../messages/en.json";
import am from "../messages/am.json";
import om from "../messages/om.json";

const CATALOGS = { en, am, om } as const;
type Locale = keyof typeof CATALOGS;

for (const locale of ["en", "am", "om"] as Locale[]) {
  const m = CATALOGS[locale];

  test(`advisor flow end to end (${locale})`, async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto(`/${locale}/advisor`);
    await expect(page.locator("html")).toHaveAttribute("lang", locale);
    await expect(page.getByRole("heading", { level: 2, name: m.advisor.location.title })).toBeVisible();
    await waitForAdvisorReady(page);

    // Step 1 — coordinates by keyboard (no map interaction needed).
    const lat = page.getByLabel(m.advisor.location.latitude, { exact: true });
    const lon = page.getByLabel(m.advisor.location.longitude, { exact: true });
    await lat.fill("8.38");
    await lon.fill("39.37");
    await expect(lat).toHaveValue("8.38");
    await lon.press("Enter");
    await expect(page).toHaveURL(/lat=8\.38/);
    // The belt resolves from /context (debounced).
    await expect(page.getByText(m.advisor.location.zone, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: m.common.next, exact: true }).click();

    // Step 2 — challenge card.
    await expect(page.getByRole("heading", { level: 2, name: m.advisor.challenge.title })).toBeVisible();
    await page.getByRole("group", { name: m.advisor.challenge.title }).getByRole("button").nth(3).click();
    await expect(page).toHaveURL(/family=Erosion/);

    // Step 3 — objective chip (only evidence-backed objectives are offered); pick "soil loss" by its glossary label.
    await expect(page.getByRole("heading", { level: 2, name: m.advisor.objective.title })).toBeVisible();
    await page
      .getByRole("group", { name: m.advisor.objective.title })
      .getByRole("button", { name: indicatorLabel("soil loss", locale), exact: true })
      .click();
    await expect(page).toHaveURL(/indicator=soil\+loss/);

    // Step 4 — crop optional; score.
    await expect(page.getByRole("heading", { level: 2, name: m.advisor.crop.title })).toBeVisible();
    await page.getByRole("button", { name: m.advisor.getRecommendation }).click();

    // Results — context, ranked cards, source badge, honesty copy.
    await expect(page.getByRole("heading", { level: 2, name: m.advisor.results.title })).toBeVisible();
    // (the hidden print sheet repeats the heading, hence .first())
    await expect(page.getByText(m.advisor.results.context.title).first()).toBeVisible();
    const cards = page.locator("article[aria-labelledby^='practice-']");
    await expect(cards.first()).toBeVisible();
    await expect(page.getByRole("button", { name: new RegExp(m.advisor.results.source.label) })).toBeVisible();
    await expect(page.getByText(m.advisor.results.disclaimer).first()).toBeVisible();
    // The effect sentence is the API's own (0b wording) — never recomputed.
    if (locale === "en") await expect(cards.first()).toContainText(/~\d+% reduction in soil loss/);
    else await expect(cards.first()).toContainText(/~\d+%/);
    const recommendCall = calls.find((c) => c.url === "/recommend");
    expect(recommendCall?.body).toMatchObject({ lat: 8.38, lon: 39.37, indicator: "soil loss" });

    // "Why this?" opens the model's chart + note.
    await cards.first().getByRole("button", { name: m.advisor.results.card.why }).click();
    await expect(cards.first().getByRole("button", { name: m.advisor.results.card.hideWhy })).toHaveAttribute("aria-expanded", "true");
  });
}

test("a shared results URL scores immediately and survives reload", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.locator("article[aria-labelledby^='practice-']")).toHaveCount(3);
  await page.reload();
  await expect(page.locator("article[aria-labelledby^='practice-']")).toHaveCount(3);
});

test("no-evidence and API-down states are designed, not blank", async ({ page }) => {
  await mockApi(page, {
    recommend: {
      status: 422,
      body: { error: { code: "recommend_error", message: "No field evidence in the dataset for challenge 'X' with objective 'Y'." } },
    },
  });
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.getByText(en.advisor.results.noEvidence.title)).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockApi(page, { down: true });
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.getByRole("alert").filter({ hasText: en.status.apiUnreachable }).first()).toBeVisible({ timeout: 20_000 });
});

test("axe: home, advisor step 1, results, chat, about have no violations", async ({ page }) => {
  await mockApi(page);
  for (const path of ["/en", "/en/advisor", `/en/advisor?${RESULTS_QUERY}`, "/en/chat", "/en/about", "/am/advisor"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const results = await axe(page).disableRules(["color-contrast"]).analyze();
    expect(results.violations, `${path}: ${JSON.stringify(results.violations.map((v) => [v.id, v.nodes.length]))}`).toEqual([]);
    const contrast = await axe(page).withRules(["color-contrast"]).analyze();
    expect(contrast.violations.map((v) => v.nodes.map((n) => n.html)), `${path} contrast`).toEqual([]);
  }
});

test("dark mode follows the OS preference and the toggle, with the dark tokens", async ({ page }) => {
  await mockApi(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.locator("html")).toHaveClass(/dark/);
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).toBe("rgb(15, 22, 19)"); // --background dark
  await page.getByRole("button", { name: en.nav.theme.toLight }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.screenshot({ path: "test-results/dark-results.png", fullPage: false });
});

test("print sheet carries the honesty copy, the citations and the share link", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/en/advisor?${RESULTS_QUERY}`);
  await expect(page.locator("article[aria-labelledby^='practice-']").first()).toBeVisible();
  // Load the evidence as "Save as PDF" would, then emulate print media.
  await page.evaluate(() => {
    window.print = () => undefined;
  });
  await page.getByRole("button", { name: en.advisor.results.print.savePdf }).click();
  await page.emulateMedia({ media: "print" });
  const sheet = page.locator(".print-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText(en.advisor.results.disclaimer);
  await expect(sheet).toContainText(en.advisor.results.print.footer.slice(0, 40));
  await expect(sheet).toContainText(en.advisor.results.print.shareLink);
  await expect(sheet).toContainText(/~\d+% reduction in soil loss/);
  await expect(sheet).toContainText(en.advisor.results.print.sources);
  await expect(sheet).toContainText("doi:");
  // The interactive view and the app chrome are hidden in print.
  await expect(page.getByRole("banner")).toBeHidden();
  await expect(page.getByRole("button", { name: en.advisor.results.print.savePdf })).toBeHidden();
  await page.screenshot({ path: "test-results/print-preview.png", fullPage: true });
});
