import { expect, test } from "@playwright/test";
import { RESULTS_QUERY, advisoryEvent, fixture, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";
import { sourceModeLabel } from "../src/i18n/glossary";

/**
 * The evidence-tiered advisory (P9) in the three modes, in English and Amharic,
 * against /advise fixtures captured from the real backend (UTF-8). The
 * mojibake guard fails the test if any double-encoded text ("â€", "Ã") reaches
 * the page, in the fixtures or in the catalogs.
 */
const CATALOGS = { en, am } as const;
const MOJIBAKE = /â€|Ã./;
const NUMBERS = /[%±]/;
const BASE = "lat=8.38&lon=39.37&family=Erosion+control+and+water+management";
const PRACTICE_CARDS = "article[aria-labelledby^='practice-']";

for (const locale of ["en", "am"] as const) {
  const m = CATALOGS[locale];

  test(`model-led: the ranking alone, badge says model (${locale})`, async ({ page }) => {
    const calls = await mockApi(page);
    await page.goto(`/${locale}/advisor?${BASE}&indicator=water+use+efficiency&top=3`);
    await page.locator(PRACTICE_CARDS).first().waitFor();
    const badge = page.getByTestId("mode-badge").first();
    await expect(badge).toHaveAttribute("data-mode", "model-led");
    await expect(badge).toContainText(sourceModeLabel("model", locale));
    await expect(page.getByTestId("documented-practices")).toHaveCount(0);
    await expect(page.getByTestId("mode-reasons")).toHaveCount(0);
    // Results come from /advise (one call, in the UI language); /recommend is not called by the page.
    expect(calls.find((c) => c.url === "/advise")?.body).toMatchObject({ indicator: "water use efficiency", language: locale, top_n: 3 });
    expect(calls.some((c) => c.url === "/recommend")).toBe(false);
    expect(await page.locator("body").innerText()).not.toMatch(MOJIBAKE);
  });

  test(`hybrid: ranking plus documented practices, with sources and no effect numbers (${locale})`, async ({ page }) => {
    await mockApi(page);
    await page.goto(`/${locale}/advisor?${RESULTS_QUERY}`);
    await page.locator(PRACTICE_CARDS).first().waitFor();
    await expect(page.getByTestId("mode-badge").first()).toHaveAttribute("data-mode", "hybrid");
    const reasons = page.getByTestId("mode-reasons");
    await expect(reasons).toBeVisible();
    await expect(reasons).toContainText(m.advisor.results.mode.explain.hybrid);
    const docs = page.getByTestId("documented-practices");
    await expect(docs).toBeVisible();
    await expect(docs.getByRole("heading", { name: m.advisor.results.documented.title })).toBeVisible();
    const cards = docs.getByTestId("documented-card");
    const n = await cards.count();
    expect(n).toBeGreaterThan(0);
    expect(n).toBeLessThanOrEqual(5);
    const text = await docs.innerText();
    expect(text).toContain(m.advisor.results.documented.why);
    expect(text).not.toMatch(NUMBERS);
    // Every card cites at least one numbered source ([n] study, [Gn] guidance, [Wn] record).
    for (let i = 0; i < n; i++) {
      await expect(cards.nth(i).getByText(/^\[(G|W)?\d+\]$/).first()).toBeVisible();
    }
    // The print sheet carries the mode and the documented practices.
    const sheet = page.locator("article.print-sheet");
    await expect(sheet).toContainText(sourceModeLabel("hybrid", locale));
    await expect(sheet).toContainText(m.advisor.results.documented.title);
    await expect(sheet).toContainText(m.advisor.results.documented.why);
    expect(await page.locator("body").innerText()).not.toMatch(MOJIBAKE);
  });

  test(`knowledge-led: no ranking; documented practices replace the no-evidence error (${locale})`, async ({ page }) => {
    // The stepper only offers evidence-backed objectives, so an unsupported pair
    // cannot be reached by URL; the knowledge-led answer is mocked onto the demo request
    // (the backend returns exactly this shape when the engine has no evidence at a pin).
    await mockApi(page, { advise: "knowledge" });
    await page.goto(`/${locale}/advisor?${RESULTS_QUERY}`);
    await expect(page.getByTestId("knowledge-led")).toBeVisible();
    await expect(page.getByText(m.advisor.results.knowledgeLed.title, { exact: true }).first()).toBeVisible();
    await expect(page.locator(PRACTICE_CARDS)).toHaveCount(0);
    await expect(page.getByTestId("mode-badge").first()).toHaveAttribute("data-mode", "knowledge-led");
    await expect(page.getByTestId("mode-reasons")).toContainText(m.advisor.results.mode.reason.engine_unsupported);
    const docs = page.getByTestId("documented-practices");
    await expect(docs).toBeVisible();
    expect(await docs.getByTestId("documented-card").count()).toBeGreaterThan(0);
    expect(await docs.innerText()).not.toMatch(NUMBERS);
    // Context card still shows the resolved belt; print sheet says "documented practice".
    await expect(page.getByText(m.advisor.results.context.title).first()).toBeVisible();
    const sheet = page.locator("article.print-sheet");
    await expect(sheet).toContainText(sourceModeLabel("documented", locale));
    await expect(sheet).toContainText(m.advisor.results.documented.title);
    expect(await page.locator("body").innerText()).not.toMatch(MOJIBAKE);
  });
}

test("chat: hybrid answers carry the documented practices inline, under the ranking", async ({ page }) => {
  await mockApi(page);
  await page.goto("/en/chat");
  await page.getByRole("textbox", { name: en.chat.message }).fill("My farm is at 8.38, 39.37 and I want to reduce erosion.");
  await page.getByRole("button", { name: en.chat.ask }).click();
  const rec = page.getByTestId("chat-recommendation");
  await expect(rec).toBeVisible();
  await expect(rec.getByTestId("mode-badge").first()).toHaveAttribute("data-mode", "hybrid");
  const docs = rec.getByTestId("chat-documented");
  await expect(docs).toBeVisible();
  await expect(docs).toContainText(en.chat.advisory.hybrid);
  expect(await docs.getByTestId("documented-card").count()).toBeGreaterThan(0);
  expect(await docs.innerText()).not.toMatch(NUMBERS);
  expect(await page.locator("body").innerText()).not.toMatch(MOJIBAKE);
});

test("chat: a knowledge-led answer has no ranking, lists documented practices and deep-links to the Advisor", async ({ page }) => {
  const slots = fixture<Record<string, unknown>>("chat-slots");
  await mockApi(page, {
    chatEvents: [
      { type: "slots", data: { ...slots, indicator: "income" } },
      { type: "advisory", data: advisoryEvent("knowledge") },
      { type: "token", text: "There is no field-trial evidence for income in this challenge; " },
      { type: "token", text: "documented practices are listed instead." },
      { type: "done" },
    ],
  });
  await page.goto("/en/chat");
  await page.getByRole("textbox", { name: en.chat.message }).fill("My farm is at 8.38, 39.37; erosion control; I want more income.");
  await page.getByRole("button", { name: en.chat.ask }).click();
  const turn = page.getByTestId("chat-knowledge-led");
  await expect(turn).toBeVisible();
  await expect(page.getByTestId("chat-recommendation")).toHaveCount(0);
  await expect(turn.getByTestId("mode-badge")).toHaveAttribute("data-mode", "knowledge-led");
  await expect(turn).toContainText(en.chat.advisory.knowledgeLed);
  expect(await turn.getByTestId("documented-card").count()).toBeGreaterThan(0);
  await expect(page.getByRole("log").getByText(/documented practices are listed instead/)).toBeVisible();
  // The setup is complete: no quick-reply chips re-appear; the Advisor link carries the slots.
  await expect(page.getByTestId("quick-replies")).toHaveCount(0);
  await expect(turn.getByRole("link", { name: en.chat.openInAdvisor })).toHaveAttribute("href", /indicator=income/);
  expect(await page.locator("body").innerText()).not.toMatch(MOJIBAKE);
});

test("documentation screenshots: the three modes in English and Amharic", async ({ page }) => {
  test.setTimeout(120_000);
  await mockApi(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const locale of ["en", "am"] as const) {
    for (const [mode, fixture, indicator] of [
      ["model-led", "model", "water+use+efficiency"],
      ["hybrid", "hybrid", "soil+loss"],
      ["knowledge-led", "knowledge", "soil+loss"],
    ] as const) {
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await mockApi(page, { advise: fixture });
      await page.goto(`/${locale}/advisor?${BASE}&indicator=${indicator}&top=3`);
      await page.getByTestId("mode-badge").first().waitFor();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `test-results/shots/p9-${mode}-${locale}.png`, fullPage: true });
    }
  }
});
