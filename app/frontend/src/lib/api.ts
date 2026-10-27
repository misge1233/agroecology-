import type {
  ApiLanguage,
  ChatMessage,
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
  const res = await fetch(`${API_BASE}/metadata`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchContext(
  lat: number,
  lon: number,
  signal?: AbortSignal
): Promise<ContextResponse> {
  const res = await fetch(
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
  const res = await fetch(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function postExplain(
  recommendation: RecommendResponse,
  opts?: { question?: string; k?: number; signal?: AbortSignal; language?: ApiLanguage }
): Promise<ExplainResponse> {
  const res = await fetch(`${API_BASE}/explain`, {
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
  const res = await fetch(`${API_BASE}/geocode?q=${encodeURIComponent(q)}`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export { API_BASE };
