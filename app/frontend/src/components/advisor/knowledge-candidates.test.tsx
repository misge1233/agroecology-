// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../messages/en.json";
import am from "../../../messages/am.json";
import om from "../../../messages/om.json";
import type { KnowledgeCandidate } from "@/lib/types";
import { KnowledgeCandidates, candidateLabel } from "./knowledge-candidates";

const CATALOGS = { en, am, om } as const;

export const CANDIDATES: KnowledgeCandidate[] = [
  {
    key: "Mulch",
    component: "Mulch",
    label: "Mulch",
    practices: ["Mulch-Water Harvesting", "Mulch"],
    sources: ["evidence_other_objectives", "documented_in_guidance"],
    support: { n_sources: 2, n_documents: 3, n_guidance_documents: 1, n_studies: 2, n_passages: 2, other_objectives: { yield: 2 } },
    record: null,
    citations: [
      { tier: "evidence", ref: "1", era_code: "T0001", title: "Mulching trials in Tigray", year: 2019, doi: "10.1/x", url: null, snippet: "…", indicator: "yield", practice: "Mulch" },
      { tier: "evidence", ref: "2", era_code: "T0002", title: "Residue cover and maize yield", year: 2021, doi: null, url: null, snippet: null, indicator: "yield", practice: "Mulch" },
      { tier: "guidance", ref: "G1", era_code: null, title: "Mulching guide", year: 2020, doi: null, url: "https://example.org/mulch.pdf", snippet: "Mulch reduces runoff", indicator: null, practice: null },
    ],
    rationale: { key: "kc.rationale.guidance", params: { n_docs: 1 } },
    rationale_text: "Described in 1 guidance document and measured for other objectives in 2 studies.",
  },
  {
    key: "Physical SWC Measures",
    component: "Physical SWC Measures",
    label: "Physical SWC Measures",
    practices: ["Physical SWC Measures"],
    sources: ["documented_practice_record"],
    support: { n_sources: 1, n_documents: 1, n_guidance_documents: 0, n_studies: 0, n_passages: 0, other_objectives: {} },
    record: { wocat_id: "T_123", country: "Ethiopia", shared_context: ["Dry Kolla"] },
    citations: [{ tier: "practice", ref: "W1", title: "Stone bunds, Tigray", wocat_id: "T_123", country: "Ethiopia", url: "https://qcat.wocat.net/T_123" }],
    rationale: { key: "kc.rationale.record", params: {} },
    rationale_text: "Documented as a practice record from a comparable setting.",
  },
];

function renderCandidates(locale: keyof typeof CATALOGS, mode: "hybrid" | "knowledge-led", candidates = CANDIDATES) {
  return render(
    <NextIntlClientProvider locale={locale} messages={CATALOGS[locale]}>
      <KnowledgeCandidates candidates={candidates} mode={mode} />
    </NextIntlClientProvider>
  );
}

describe("KnowledgeCandidates", () => {
  it("lists documented practices with sources, rationale and numbered citations — never an effect number", () => {
    renderCandidates("en", "hybrid");
    expect(screen.getByRole("heading", { name: en.advisor.results.documented.title })).toBeInTheDocument();
    expect(screen.getByText(en.advisor.results.documented.introHybrid)).toBeInTheDocument();
    const cards = screen.getAllByTestId("documented-card");
    expect(cards).toHaveLength(2);
    expect(screen.getByText("Mulch")).toBeInTheDocument();
    expect(screen.getByText(/Described in 1 guidance document/)).toBeInTheDocument();
    expect(screen.getByText(en.advisor.results.documented.source.evidence_other_objectives)).toBeInTheDocument();
    expect(screen.getByText(en.advisor.results.documented.source.documented_in_guidance)).toBeInTheDocument();
    // "Practice record" is both the source badge and the citation's tier chip.
    expect(screen.getAllByText(en.advisor.results.documented.source.documented_practice_record).length).toBeGreaterThan(0);
    // Citations carry the per-study / per-document / per-record markers.
    expect(screen.getByText("[1]")).toBeInTheDocument();
    expect(screen.getByText("[G1]")).toBeInTheDocument();
    expect(screen.getByText("[W1]")).toBeInTheDocument();
    const guide = screen.getByRole("link", { name: /Mulching guide/ });
    expect(guide).toHaveAttribute("href", "https://example.org/mulch.pdf");
    expect(screen.getByRole("link", { name: /Mulching trials/ })).toHaveAttribute("href", "https://doi.org/10.1/x");
    // No "%" and no "±" anywhere: documented practices are never quantified.
    expect(document.body.textContent).not.toMatch(/[%±]/);
  });

  it("says so when there is no documented practice (knowledge-led)", () => {
    renderCandidates("en", "knowledge-led", []);
    expect(screen.getByText(en.advisor.results.documented.empty)).toBeInTheDocument();
  });

  it("uses the glossary label for the component in Amharic and Afaan Oromoo", () => {
    expect(candidateLabel(CANDIDATES[0], "am")).not.toBe("Mulch");
    expect(candidateLabel(CANDIDATES[0], "om")).not.toBe("Mulch");
    renderCandidates("am", "knowledge-led");
    expect(screen.getByText(am.advisor.results.documented.introKnowledge)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: candidateLabel(CANDIDATES[0], "am") })).toBeInTheDocument();
  });
});
