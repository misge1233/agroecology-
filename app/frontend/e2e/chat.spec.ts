import { expect, test } from "@playwright/test";
import { API_BASE, defaultChatEvents, fixture, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";

test("chat happy path: streamed answer, inline result card, Open in Advisor", async ({ page }) => {
  // A slow answer keeps the "thinking" state on screen long enough to assert it.
  const calls = await mockApi(page, { delayMs: 1200 });
  await page.goto("/en/chat");
  await page.getByRole("textbox", { name: en.chat.message }).fill("My farm is at 8.38, 39.37 and I want to reduce erosion.");
  await page.getByRole("button", { name: en.chat.ask }).click();

  // Explicit states: thinking → (scoring) → streaming → done, with timestamps.
  await expect(page.getByTestId("chat-status")).toBeVisible();
  const log = page.getByRole("log", { name: en.a11y.chatLog });
  await expect(log.getByText(en.chat.roles.user + " ·")).toBeVisible();
  await expect(page.getByTestId("chat-recommendation")).toBeVisible();
  await expect(page.getByText(en.chat.contextTitle)).toBeVisible();
  await expect(log.locator("article[aria-labelledby^='practice-']").first()).toBeVisible();
  await expect(log.getByText(/Mulch-Water Harvesting/).first()).toBeVisible();
  await expect(page.getByTestId("chat-status")).toBeHidden();
  await expect(log.getByText(en.chat.roles.assistant + " ·")).toBeVisible();

  const chatCall = calls.find((c) => c.url === "/chat");
  expect(chatCall?.body).toMatchObject({ language: "en", stream: true, hint: null });

  // Deep link to the Advisor carries the scored query.
  const open = page.getByRole("link", { name: en.chat.openInAdvisor });
  await expect(open).toHaveAttribute("href", /\/en\/advisor\?.*lat=8\.38.*indicator=soil\+loss/);
});

test("quick-reply chips send a translated sentence plus a structured hint (am)", async ({ page }) => {
  const slots = fixture<Record<string, unknown>>("chat-slots");
  const calls = await mockApi(page, {
    chatEvents: [
      { type: "slots", data: { ...slots, practice_family: null, indicator: null, lat: null, lon: null, missing: ["challenge", "objective", "location"], is_complete: false } },
      { type: "token", text: am.chat.intro },
      { type: "done" },
    ],
  });
  await page.goto("/am/chat");
  await page.getByRole("textbox", { name: am.chat.message }).fill("ሰላም");
  await page.getByRole("button", { name: am.chat.ask }).click();
  const quick = page.getByTestId("quick-replies");
  await expect(quick).toBeVisible();
  await quick.getByRole("group", { name: am.chat.quick.chooseChallenge }).getByRole("button").nth(3).click();

  const chip = calls.filter((c) => c.url === "/chat").at(-1);
  expect(chip?.body).toMatchObject({ language: "am", hint: { practice_family: "Erosion control and water management" } });
  const sent = (chip?.body as { message: string }).message;
  expect(sent).toMatch(/[ሀ-፿]/);
  expect(sent).not.toContain("Erosion control and water management");
  await expect(page.getByRole("log").getByText(sent)).toBeVisible();
});

test("a failed stream shows an error state with a working retry", async ({ page }) => {
  let attempt = 0;
  await mockApi(page);
  await page.route(`${API_BASE}/chat`, (route) => {
    attempt += 1;
    if (attempt === 1) return route.abort("failed");
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: defaultChatEvents().map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
    });
  });
  await page.goto("/en/chat");
  await page.getByRole("textbox", { name: en.chat.message }).fill("My farm is at 8.38, 39.37 and I want to reduce erosion.");
  await page.getByRole("button", { name: en.chat.ask }).click();
  await expect(page.getByText(en.chat.errorTitle)).toBeVisible();
  await page.getByRole("button", { name: en.chat.retrySend }).click();
  await expect(page.getByTestId("chat-recommendation")).toBeVisible();
  expect(attempt).toBe(2);
});

test("Pick on map opens the map sheet", async ({ page }) => {
  await mockApi(page);
  await page.goto("/en/chat");
  await page.getByRole("button", { name: en.chat.pickOnMap }).first().click();
  const dialog = page.getByRole("dialog", { name: en.chat.pickLocation });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".leaflet-container")).toBeVisible();
  await dialog.getByLabel(en.advisor.location.latitude, { exact: true }).fill("8.38");
  await dialog.getByLabel(en.advisor.location.longitude, { exact: true }).fill("39.37");
  await dialog.getByLabel(en.advisor.location.longitude, { exact: true }).press("Enter");
  await expect(dialog.getByRole("button", { name: en.chat.useThisLocation })).toBeEnabled();
});
