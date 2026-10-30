import type { Page, Route } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Browser-side API mock. Every call the app makes to NEXT_PUBLIC_API_BASE_URL
 * is answered from `e2e/fixtures/*.json`, which were captured from the real
 * FastAPI responses (U2), so the shapes are the contract's own. Map tiles are
 * answered with a 1×1 PNG so the suite never touches the network.
 */
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const FIXTURES = path.resolve(__dirname, "..", "fixtures");
const cache = new Map<string, unknown>();
export function fixture<T = unknown>(name: string): T {
  if (!cache.has(name)) {
    cache.set(name, JSON.parse(fs.readFileSync(path.join(FIXTURES, `${name}.json`), "utf8")));
  }
  return structuredClone(cache.get(name)) as T;
}

export function hasFixture(name: string): boolean {
  return fs.existsSync(path.join(FIXTURES, `${name}.json`));
}

const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64"
);

export type AdviseFixtureName = "model" | "hybrid" | "knowledge";

/**
 * Which captured /advise answer fits a request (P9). The three fixtures were
 * captured at the demo pin (8.38, 39.37 — Dry Kolla) for the Erosion-control
 * challenge: water use efficiency is model-led, soil loss is hybrid and income
 * (not scored by the model) is knowledge-led.
 */
export function adviseFixtureFor(indicator: string | undefined): AdviseFixtureName {
  if (indicator === "income") return "knowledge";
  if (indicator === "water use efficiency") return "model";
  return "hybrid";
}

/** The chat `advisory` SSE event derived from a captured /advise answer. */
export function advisoryEvent(name: AdviseFixtureName): Record<string, unknown> {
  const adv = fixture<Record<string, unknown> & { model: { query: Record<string, unknown> } | null }>(`advise-${name}`);
  const { mode, reasons, knowledge_candidates, evidence_sufficiency, context, model } = adv;
  const rest = { mode, reasons, knowledge_candidates, evidence_sufficiency, context };
  const query = model?.query ?? {
    lat: 8.38,
    lon: 39.37,
    practice_family: "Erosion control and water management",
    indicator: name === "knowledge" ? "income" : "soil loss",
    crop_type: null,
  };
  return { ...rest, query };
}

export interface MockOptions {
  /** Simulate an unreachable API: every call fails at the network level. */
  down?: boolean;
  /** Override the /recommend answer (e.g. an error envelope). */
  recommend?: { status: number; body: unknown };
  /** Force one /advise fixture, or an arbitrary answer (e.g. an error envelope). */
  advise?: AdviseFixtureName | { status: number; body: unknown };
  /** Extra latency per call, to make loading states observable. */
  delayMs?: number;
  /** Events the chat stream should emit (SSE). */
  chatEvents?: unknown[];
  /** Fail map tiles (low-bandwidth behaviour). */
  tilesFail?: boolean;
  /** Record of calls for assertions. */
  calls?: { method: string; url: string; body?: unknown }[];
}

function sse(events: unknown[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

/** The default chat answer: slots → advisory → recommendation → a short narrative → done. */
export function defaultChatEvents(): unknown[] {
  return [
    { type: "slots", data: fixture("chat-slots") },
    { type: "advisory", data: advisoryEvent("hybrid") },
    { type: "recommendation", data: fixture("recommend") },
    { type: "token", text: "For your **Dry Kolla** area, the evidence ranks " },
    { type: "token", text: "**Mulch-Water Harvesting** to reduce soil loss." },
    { type: "done" },
  ];
}

export async function mockApi(page: Page, opts: MockOptions = {}) {
  const calls = opts.calls ?? [];
  const json = async (route: Route, body: unknown, status = 200) => {
    if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  };

  await page.route(/tile\.openstreetmap\.org/, (route) =>
    opts.tilesFail ? route.abort("failed") : route.fulfill({ status: 200, contentType: "image/png", body: PNG_1X1 })
  );

  await page.route(`${API_BASE}/**`, async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    let body: unknown;
    try {
      body = req.postDataJSON();
    } catch {
      body = undefined;
    }
    calls.push({ method: req.method(), url: url.pathname + url.search, body });

    if (opts.down) return route.abort("connectionrefused");

    switch (url.pathname) {
      case "/health":
        return json(route, fixture("health"));
      case "/metadata":
        return json(route, fixture("metadata"));
      case "/context":
        return json(route, fixture("context"));
      case "/geocode": {
        const q = (url.searchParams.get("q") || "").toLowerCase();
        return json(
          route,
          q.includes("debre")
            ? fixture("geocode")
            : { query: q, found: false, name: null, lat: null, lon: null, source: null }
        );
      }
      case "/recommend": {
        if (opts.recommend) return json(route, opts.recommend.body, opts.recommend.status);
        const rec = fixture<{ recommendations: unknown[]; details: { ranked: unknown[] } }>("recommend");
        const topN = Number((body as { top_n?: number } | undefined)?.top_n ?? 1);
        rec.recommendations = rec.recommendations.slice(0, topN);
        rec.details.ranked = rec.details.ranked.slice(0, topN);
        return json(route, rec);
      }
      case "/advise": {
        if (opts.advise && typeof opts.advise === "object") return json(route, opts.advise.body, opts.advise.status);
        const req = body as { indicator?: string; top_n?: number; language?: string } | undefined;
        const name = typeof opts.advise === "string" ? opts.advise : adviseFixtureFor(req?.indicator);
        // Rationales and the knowledge-led text are produced server-side in the UI
        // language: `advise-<name>.<lang>.json` holds the am/om captures.
        const lang = req?.language && req.language !== "en" ? req.language : null;
        const adv = fixture<{ model: { recommendations: unknown[]; details: { ranked: unknown[] } } | null }>(
          lang && hasFixture(`advise-${name}.${lang}`) ? `advise-${name}.${lang}` : `advise-${name}`
        );
        if (adv.model) {
          const topN = Number(req?.top_n ?? 3);
          adv.model.recommendations = adv.model.recommendations.slice(0, topN);
          adv.model.details.ranked = adv.model.details.ranked.slice(0, topN);
        }
        return json(route, adv);
      }
      case "/explain":
        return json(route, fixture("explain"));
      case "/chat":
        if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
        return route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: sse(opts.chatEvents ?? defaultChatEvents()),
        });
      default:
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "not_found", message: url.pathname } }),
        });
    }
  });
  return calls;
}

/** Results URL for the canonical demo request (same values as the fixtures). */
export const RESULTS_QUERY =
  "lat=8.38&lon=39.37&family=Erosion+control+and+water+management&indicator=soil+loss&top=3";

/** `document.scrollWidth <= window.innerWidth` — the 0a guard, with culprits. */
export async function horizontalOverflow(
  page: Page
): Promise<{ scrollWidth: number; innerWidth: number; offenders: string[] }> {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const offenders: string[] = [];
    if (doc.scrollWidth > window.innerWidth) {
      for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
        const r = el.getBoundingClientRect();
        if (r.right > window.innerWidth + 1 && r.width > 0) {
          const cls = String(el.className || "").split(" ").slice(0, 4).join(".");
          offenders.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${cls} right=${Math.round(r.right)}`);
          if (offenders.length >= 8) break;
        }
      }
    }
    return { scrollWidth: doc.scrollWidth, innerWidth: window.innerWidth, offenders };
  });
}

/**
 * Wait until React has hydrated the Advisor's location step: on desktop the
 * map mounts after hydration; on phones the "Show the map" button appears.
 * Typing into a server-rendered input before hydration loses the keystrokes.
 */
export async function waitForAdvisorReady(page: Page) {
  await page.locator(".leaflet-container, button:has(svg.lucide-map-pin)").first().waitFor({ state: "visible", timeout: 20_000 });
}
