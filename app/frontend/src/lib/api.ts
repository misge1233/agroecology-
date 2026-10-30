import { retryFinished, retryStarted } from "./retry-store";
import type {
  AdviseResponse,
  ApiLanguage,
  ChatMessage,
  ChatSlotsHint,
  ChatStreamEvent,
  ContextResponse,
  ExplainResponse,
  GeocodeResponse,
  Metadata,
  RecommendRequest,
  RecommendResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

/**
 * Bounded retry with backoff for idempotent calls (U2 item 5): a network
 * failure or a 502/503/504 is retried after 600 ms and 1800 ms, then surfaces.
 * Aborted requests are never retried; the chat stream is not routed through
 * here (a half-streamed answer must not be replayed).
 */
export const RETRY_DELAYS_MS = [600, 1800];
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function fetchWithRetry(input: string, init: RequestInit = {}): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(input, init);
      const transient = res.status === 502 || res.status === 503 || res.status === 504;
      if (!transient || attempt >= RETRY_DELAYS_MS.length) return res;
    } catch (e) {
      if (init.signal?.aborted || attempt >= RETRY_DELAYS_MS.length) throw e;
    }
    retryStarted();
    try {
      await sleep(RETRY_DELAYS_MS[attempt]);
    } finally {
      retryFinished();
    }
    if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const err = body?.error || body?.detail?.error || body?.detail;
    if (typeof err === "string") return err;
    if (err?.message) return err.message;
    // Pydantic validation array
    if (Array.isArray(err) && err[0]?.msg) return err[0].msg;
    return JSON.stringify(body);
  } catch {
    return res.statusText || "Request failed";
  }
}

export async function fetchMetadata(): Promise<Metadata> {
  const res = await fetchWithRetry(`${API_BASE}/metadata`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchContext(
  lat: number,
  lon: number,
  signal?: AbortSignal
): Promise<ContextResponse> {
  const res = await fetchWithRetry(
    `${API_BASE}/context?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
    { cache: "no-store", signal }
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function postRecommend(
  body: RecommendRequest,
  signal?: AbortSignal
): Promise<RecommendResponse> {
  const res = await fetchWithRetry(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** The evidence-tiered advisory (P9): /recommend wrapped with mode + knowledge candidates. */
export async function postAdvise(
  body: RecommendRequest & { language?: ApiLanguage },
  signal?: AbortSignal
): Promise<AdviseResponse> {
  const res = await fetchWithRetry(`${API_BASE}/advise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, language: body.language ?? "en" }),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function postExplain(
  recommendation: RecommendResponse,
  opts?: { question?: string; k?: number; signal?: AbortSignal; language?: ApiLanguage }
): Promise<ExplainResponse> {
  const res = await fetchWithRetry(`${API_BASE}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      recommendation,
      question: opts?.question ?? null,
      k: opts?.k ?? 8,
      // U1: the explanation is written in the UI language; numbers stay the model's.
      language: opts?.language ?? "en",
    }),
    signal: opts?.signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function* streamChat(opts: {
  message: string;
  history: ChatMessage[];
  lastRecommendation?: RecommendResponse | null;
  topN?: number;
  signal?: AbortSignal;
  language?: ApiLanguage;
  /** Structured values behind a quick-reply chip (U2). */
  hint?: ChatSlotsHint | null;
}): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      message: opts.message,
      history: opts.history,
      last_recommendation: opts.lastRecommendation ?? null,
      stream: true,
      top_n: opts.topN ?? 1,
      language: opts.language ?? "en",
      hint: opts.hint ?? null,
    }),
    signal: opts.signal,
  });

  if (!res.ok) throw new Error(await parseError(res));
  if (!res.body) throw new Error("No response stream");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        yield JSON.parse(raw) as ChatStreamEvent;
      } catch {
        // ignore malformed chunk
      }
    }
  }
}

/** Offline gazetteer lookup for the Advisor's place search (U1). */
export async function fetchGeocode(q: string, signal?: AbortSignal): Promise<GeocodeResponse> {
  const res = await fetchWithRetry(`${API_BASE}/geocode?q=${encodeURIComponent(q)}`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export { API_BASE };
