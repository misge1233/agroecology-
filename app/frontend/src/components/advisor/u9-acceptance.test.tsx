// @vitest-environment jsdom
/**
 * U9 acceptance (frontend): fused headline and source chip on the card (D1),
 * no Markdown syntax in the Evidence text (B3), ICU plurals (D3), and one
 * label per source across lists (B4).
 */
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider, createTranslator } from "next-intl";
import en from "../../../messages/en.json";
import am from "../../../messages/am.json";
import om from "../../../messages/om.json";
import type { ExplainResponse, PracticeEvidence, RecommendResponse } from "@/lib/types";
import { buildRegistry } from "@/lib/citation-registry";
import { EvidenceBody, ExplainProvider, useExplain } from "@/components/evidence-panel";
import { CitationsProvider } from "@/components/citations";
import { ResultCard } from "./result-card";

vi.mock("@/components/practice-image", () => ({
  // eslint-disable-next-line @next/next/no-img-element
  PracticeImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
vi.mock("@/components/pct-chart", () => ({ PctChangeChart: () => <div data-testid="chart" /> }));

const EXPLAIN: ExplainResponse = {
  explanation:
    "### Why mulch\n**Mulch** cut soil loss in study plots [1]. The model estimate for your area is about 76% less soil loss.\n\n- **Covers** the soil [1]",
  citations: [
    { era_code: "NN0001", tier: "evidence", doi: null, url: null, title: "Mulch trial", year: 2019, journal: null, practice: "Mulch", snippet: "", n_passages: 1, ref: "1" },
  ],
  grounded: true,
  llm_used: true,
};
vi.mock("@/lib/api", () => ({ postExplain: vi.fn(async () => EXPLAIN) }));

const data: RecommendResponse = {
  query: { lat: 8.38, lon: 39.37, practice_family: "Erosion control and watershed management", indicator: "soil loss", crop_type: null, goal_direction: "reduce" },
  recommendations: [{ practice: "Mulch", effect: "~76% reduction in soil loss" }],
  details: {
    context: { aez_belt: "Dry Kolla" },
    crop_group: null,
    confidence: "low",
    ranked: [{ practice: "Mulch", pct_change: -76.2, log_ratio: -1.43, n_evidence: 12 }],
    n_candidates: 8,
    n_grounded: 4,
    note: "Effects are model estimates.",
  },
};

const num = (value: number, source: "model" | "study", ref: string | null = null) => ({
  value, unit: "%", source, ref, display: `${Math.round(Math.abs(value))}`,
});

const bundle: PracticeEvidence = {
  practice: "Mulch",
  lead_source: "study",
  match: "belt_group",
  headline: num(-71, "study", "S1"),
  disagreement: false,
  caution: false,
  model: { ...num(-76.2, "model"), confidence: "low", n_obs: 12, n_studies: 2, n_obs_in_zone: 0, se_log: 0.4 },
  study: { ...num(-71, "study", "S1"), refs: ["S1"], match: "belt_group", n_studies: 2, n_obs: 9 },
  studies: [],
  conservative_bound: -40,
};

describe("U9 result card (D1)", () => {
  it("leads with a plain headline from the bundle and one source chip", () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <ExplainProvider data={data} ragReady={false} graphReady={false}>
          <ResultCard item={data.recommendations[0]} ranked={data.details.ranked[0]} rank={1} data={data} bundle={bundle} />
        </ExplainProvider>
      </NextIntlClientProvider>
    );
    expect(screen.getByText("About 71% less soil loss")).toBeInTheDocument();
    expect(screen.getByText("Field study · similar area")).toBeInTheDocument();
    // The engine's own sentence is not the headline any more.
    expect(screen.queryByText("~76% reduction in soil loss")).toBeNull();
  });
});

function LoadOnMount() {
  const { load } = useExplain();
  useEffect(() => {
    void load();
  }, [load]);
  return null;
}

describe("U9 Evidence text (B3)", () => {
  it("renders Markdown as structure, never as literal ### or ** text", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={en}>
        <ExplainProvider data={data} ragReady graphReady={false}>
          <CitationsProvider lists={[]}>
            <LoadOnMount />
            <EvidenceBody practice="Mulch" />
          </CitationsProvider>
        </ExplainProvider>
      </NextIntlClientProvider>
    );
    const text = await screen.findByTestId("evidence-text");
    expect(text.textContent).not.toMatch(/###|\*\*/);
    expect(text.textContent).toContain("Mulch");
    expect(text.textContent).toContain("[1]");
  });
});

describe("U9 plurals (D3)", () => {
  const reason = (messages: typeof en, locale: string, n: number) =>
    createTranslator({ locale, messages, namespace: "advisor.results.mode.reason" })("strong_evidence", {
      practice: "Mulch",
      n_studies: n,
      n_obs: n,
    });
  it("says 1 study, not 1 studies (en)", () => {
    expect(reason(en, "en", 1)).toBe("Mulch has 1 study and 1 field observation for this objective.");
    expect(reason(en, "en", 3)).toBe("Mulch has 3 studies and 3 field observations for this objective.");
  });
  it("renders every count message in am and om without ICU errors", () => {
    for (const [messages, locale] of [[am, "am"], [om, "om"]] as const) {
      for (const n of [1, 2]) expect(reason(messages as typeof en, locale, n)).toContain(String(n));
    }
  });
});

describe("U9 citation registry (B4)", () => {
  it("gives one source one label across the cards, documented practices and explanation", () => {
    const cards = [{ tier: "evidence", era_code: "NN0001" }, { tier: "evidence", study_no: "CSA_18" }];
    const documented = [{ tier: "evidence", study_no: "CSA_18" }, { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/1" }];
    const explained = [{ tier: "evidence", era_code: "NN0001", ref: "3" }, { tier: "guidance", url: "https://cgspace.cgiar.org/handle/10568/1", ref: "G4" }];
    const reg = buildRegistry(cards, documented, explained);
    expect(reg.size).toBe(3);
    const labels = [...cards, ...documented, ...explained].map((c) => reg.label(c));
    expect(new Set(labels)).toEqual(new Set(["1", "2", "G1"]));
  });
});
