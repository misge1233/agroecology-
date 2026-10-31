import { expect, test, type Page } from "@playwright/test";
import { API_BASE, defaultChatEvents, fixture, mockApi } from "./support/api";
import en from "../messages/en.json";
import am from "../messages/am.json";

test("chat happy path: streamed answer, compact evidence, Open in Advisor", async ({ page }) => {
  // A slow answer keeps the "thinking" state on screen long enough to assert it.
  const calls = await mockApi(page, { delayMs: 1200 });
  await page.goto("/en/chat");
  await page.getByRole("textbox", { name: en.chat.message }).fill("My farm is at 8.38, 39.37 and I want to reduce erosion.");
  await page.getByRole("button", { name: en.chat.ask }).click();

  // Explicit states: thinking → (scoring) → streaming → done, with timestamps.
  await expect(page.getByTestId("chat-status")).toBeVisible();
  const log = page.getByRole("log", { name: en.a11y.chatLog });
  await expect(log.getByText(en.chat.roles.user + " ·")).toBeVisible();
  const evidence = page.getByTestId("chat-recommendation");
  await expect(evidence).toBeVisible();
  await expect(evidence).toContainText(en.chat.evidence.title);
  await expect(log.getByText(/Mulch-Water Harvesting/).first()).toBeVisible();
  await expect(page.getByTestId("chat-status")).toBeHidden();
  await expect(log.getByText(en.chat.roles.assistant + " ·")).toBeVisible();

  // Conversational: the answer asks for three practices, sends no structured hint.
  const chatCall = calls.find((c) => c.url === "/chat");
  expect(chatCall?.body).toMatchObject({ language: "en", stream: true, hint: null, top_n: 3 });

  // Deep link to the Advisor carries the scored query.
  const open = evidence.getByRole("link", { name: en.chat.openInAdvisor });
  await expect(open).toHaveAttribute("href", /\/en\/advisor\?.*lat=8\.38.*indicator=soil\+loss/);
});

test("conversational: the assistant asks in words, no buttons or forms appear, the reply is typed (am)", async ({ page }) => {
  const slots = fixture<Record<string, unknown>>("chat-slots");
  const ask = "ለመምከር ፈተናዎን፣ ዓላማዎንና ቦታዎን ይንገሩኝ።";
  const calls = await mockApi(page, {
    chatEvents: [
      { type: "slots", data: { ...slots, practice_family: null, indicator: null, lat: null, lon: null, missing: ["challenge", "objective", "location"], is_complete: false } },
      { type: "token", text: ask },
      { type: "done" },
    ],
  });
  await page.goto("/am/chat");
  await page.getByRole("textbox", { name: am.chat.message }).fill("ሰላም");
  await page.getByRole("button", { name: am.chat.ask }).click();

  const log = page.getByRole("log");
  await expect(log.getByText(ask)).toBeVisible();
  // No quick replies, chips, map offers or pickers: only the message actions.
  await expect(page.getByTestId("quick-replies")).toHaveCount(0);
  await expect(log.getByRole("group")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(log.getByRole("button", { name: am.chat.copy })).toBeVisible();

  await page.getByRole("textbox", { name: am.chat.message }).fill("ደብረ ብርሃን፣ የአፈር መሸርሸር መቀነስ");
  await page.getByRole("button", { name: am.chat.ask }).click();
  const second = calls.filter((c) => c.url === "/chat").at(-1);
  expect(second?.body).toMatchObject({ language: "am", hint: null, message: "ደብረ ብርሃን፣ የአፈር መሸርሸር መቀነስ" });
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

/** Browser speech stubs: a recognizer that "hears" one question, and a recording speaker. */
async function stubBrowserSpeech(page: Page, heard: string) {
  await page.addInitScript((text) => {
    class FakeRecognition {
      lang = "";
      onresult: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      start() {
        (window as unknown as { __recLang: string }).__recLang = this.lang;
        setTimeout(() => this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: text } }] }), 400);
        setTimeout(() => this.onend?.(), 600); // the speaker paused
      }
      stop() {
        this.onend?.();
      }
      abort() {
        this.onend?.();
      }
    }
    const w = window as unknown as Record<string, unknown>;
    w.SpeechRecognition = FakeRecognition;
    w.webkitSpeechRecognition = FakeRecognition;
    const spoken: { lang: string; text: string }[] = [];
    w.__spoken = spoken;
    w.SpeechSynthesisUtterance = class {
      lang = "";
      voice: unknown = null;
      rate = 1;
      onend: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(public text: string) {}
    };
    const synth = window.speechSynthesis;
    synth.getVoices = () => [{ lang: "en-US", name: "Test voice", voiceURI: "test" } as SpeechSynthesisVoice];
    synth.speak = (u: SpeechSynthesisUtterance) => {
      spoken.push({ lang: u.lang, text: u.text });
    };
  }, heard);
}

test("voice is hands-free: a spoken question is sent on a pause and its answer is read aloud", async ({ page }) => {
  const question = "My farm is at 8.38, 39.37 and I want to reduce soil erosion";
  await stubBrowserSpeech(page, question);
  const calls = await mockApi(page);
  await page.goto("/en/chat");
  await page.getByRole("button", { name: en.chat.voice.mic }).click();

  // No Ask press: the transcript goes straight to the advisor.
  const log = page.getByRole("log");
  await expect(log.getByText(question)).toBeVisible();
  expect(calls.filter((c) => c.url === "/chat").at(-1)?.body).toMatchObject({ message: question, language: "en" });
  expect(await page.evaluate(() => (window as unknown as { __recLang: string }).__recLang)).toBe("en-US");

  // The finished answer is handed to the speaker, figures intact.
  await expect(page.getByTestId("chat-recommendation")).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __spoken: { lang: string; text: string }[] }).__spoken.length))
    .toBeGreaterThan(0);
  const spoken = await page.evaluate(() => (window as unknown as { __spoken: { lang: string; text: string }[] }).__spoken[0]);
  expect(spoken.lang).toBe("en-US");
  expect(spoken.text).not.toMatch(/\*\*|\[\d+\]/);
});
