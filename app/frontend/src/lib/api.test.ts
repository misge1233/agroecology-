import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, RETRY_DELAYS_MS, postExplain, postRecommend, streamChat } from "./api";
import { _resetRetryForTests } from "./retry-store";
import type { ExplainResponse, RecommendResponse } from "./types";

const recommendation = {
  query: {
    lat: 8.38,
    lon: 39.37,
    practice_family: "Erosion control and water management",
    indicator: "soil loss",
    goal_direction: "decrease",
  },
  recommendations: [{ practice: "Mulching", effect: "~42% reduction in soil loss" }],
  details: { context: {}, confidence: "medium", ranked: [], n_candidates: 12, note: "" },
} as unknown as RecommendResponse;

const explainResponse: ExplainResponse = {
  explanation: "Mulching reduces soil loss on cultivated slopes [1].",
  citations: [
    {
      era_code: "NN0123",
      tier: "evidence",
      url: null,
      doi: "10.1000/xyz1",
      title: "Mulching effects on erosion",
      year: 2019,
      journal: "Catena",
      practice: "Mulching",
      snippet: "Mulch cover reduced soil loss…",
      n_passages: 2,
    },
    {
      era_code: null,
      tier: "guidance",
      url: "https://gardian.example/doc1",
      doi: null,
      title: "Mulching implementation manual",
      year: 2021,
      journal: null,
      practice: "Mulching",
      snippet: "Apply mulch after first weeding…",
      n_passages: 1,
    },
  ],
  grounded: true,
  llm_used: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  _resetRetryForTests();
});

const request = {
  lat: 8.38,
  lon: 39.37,
  practice_family: "Erosion control and water management",
  indicator: "soil loss",
  crop_type: null,
  top_n: 3,
};

describe("fetchWithRetry (U2 low-bandwidth)", () => {
  it("retries a network failure with backoff and then succeeds", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(JSON.stringify(recommendation), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = postRecommend(request);
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0]);
    expect(await pending).toEqual(recommendation);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries a 503 but gives up after the bounded attempts", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockImplementation(async () => new Response("down", { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = postRecommend(request).catch((e: Error) => e);
    await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0] + RETRY_DELAYS_MS[1] + 10);
    const result = await pending;
    expect(result).toBeInstanceOf(Error);
    expect(fetchMock).toHaveBeenCalledTimes(RETRY_DELAYS_MS.length + 1);
  });

  it("never retries a 4xx (the request is wrong, not the link)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "recommend_error", message: "No field evidence" } }), { status: 422 })
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(postRecommend(request)).rejects.toThrow("No field evidence");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("streamChat", () => {
  it("sends the language and the quick-reply hint (U2)", async () => {
    const body = "data: " + JSON.stringify({ type: "done" }) + "\n\n";
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    for await (const ev of streamChat({
      message: "ፈተናዬ የአፈር መሸርሸር መከላከልና የውሃ አያያዝ ነው።",
      history: [],
      language: "am",
      hint: { practice_family: "Erosion control and water management" },
    })) {
      events.push(ev);
    }
    expect(events).toEqual([{ type: "done" }]);
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent.language).toBe("am");
    expect(sent.hint).toEqual({ practice_family: "Erosion control and water management" });
    expect(sent.stream).toBe(true);
  });
});

describe("postExplain", () => {
  it("POSTs the recommendation to /explain and returns the parsed payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(explainResponse), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await postExplain(recommendation);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE}/explain`);
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({
      recommendation,
      question: null,
      k: 8,
      language: "en",
    });
    expect(result).toEqual(explainResponse);
    expect(result.citations[0].n_passages).toBe(2);
    // Two-tier payload (P5a): guidance citations carry tier + source url.
    expect(result.citations[1].tier).toBe("guidance");
    expect(result.citations[1].url).toBe("https://gardian.example/doc1");
  });

  it("forwards question and k when given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(explainResponse), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await postExplain(recommendation, { question: "Why mulch?", k: 4 });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.question).toBe("Why mulch?");
    expect(body.k).toBe(4);
  });

  it("throws the backend error envelope message on failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "explain_failed", message: "RAG index not built" },
        }),
        { status: 503 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(postExplain(recommendation)).rejects.toThrow("RAG index not built");
  });
});
