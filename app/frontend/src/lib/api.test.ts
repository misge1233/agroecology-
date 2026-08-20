import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE, postExplain } from "./api";
import type { ExplainResponse, RecommendResponse } from "./types";

const recommendation = {
  query: {
    lat: 8.38,
    lon: 39.37,
    practice_family: "Erosion control and water management",
    indicator: "soil loss",
    goal_direction: "decrease",
  },
  recommendations: [{ practice: "Mulching", effect: "~42% decrease in soil loss" }],
  details: { context: {}, confidence: "medium", ranked: [], n_candidates: 12, note: "" },
} as unknown as RecommendResponse;

const explainResponse: ExplainResponse = {
  explanation: "Mulching reduces soil loss on cultivated slopes [1].",
  citations: [
    {
      era_code: "NN0123",
      doi: "10.1000/xyz1",
      title: "Mulching effects on erosion",
      year: 2019,
      journal: "Catena",
      practice: "Mulching",
      snippet: "Mulch cover reduced soil loss…",
      n_passages: 2,
    },
  ],
  grounded: true,
  llm_used: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
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
    });
    expect(result).toEqual(explainResponse);
    expect(result.citations[0].n_passages).toBe(2);
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
