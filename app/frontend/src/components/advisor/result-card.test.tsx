// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../messages/en.json";
import am from "../../../messages/am.json";
import type { RecommendResponse } from "@/lib/types";
import { confidenceLabel } from "@/i18n/glossary";
import { ExplainProvider } from "@/components/evidence-panel";
import { ResultCard } from "./result-card";

vi.mock("@/components/practice-image", () => ({
  // eslint-disable-next-line @next/next/no-img-element
  PracticeImage: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
vi.mock("@/components/pct-chart", () => ({
  PctChangeChart: () => <div data-testid="chart" />,
}));

const data: RecommendResponse = {
  query: {
    lat: 8.38,
    lon: 39.37,
    practice_family: "Integrated soil fertility management",
    indicator: "soil loss",
    crop_type: null,
    goal_direction: "reduce",
  },
  recommendations: [{ practice: "Biochar-Inorganic Fertilizer", effect: "~42% reduce in soil loss" }],
  details: {
    context: { aez_belt: "Dry Dega" },
    crop_group: null,
    confidence: "medium",
    ranked: [{ practice: "Biochar-Inorganic Fertilizer", pct_change: -42.3, log_ratio: -0.55, n_evidence: 17 }],
    n_candidates: 12,
    n_grounded: 5,
    note: "Effects are model estimates.",
  },
};

function renderCard(locale: "en" | "am") {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === "en" ? en : am}>
      <ExplainProvider data={data} ragReady={false} graphReady={false}>
        <ResultCard item={data.recommendations[0]} ranked={data.details.ranked[0]} rank={1} data={data} />
      </ExplainProvider>
    </NextIntlClientProvider>
  );
}

describe("ResultCard", () => {
  it("shows the API's own effect sentence in English with confidence and evidence count", () => {
    renderCard("en");
    expect(screen.getByRole("heading", { name: "Biochar + Inorganic fertilizer" })).toBeInTheDocument();
    expect(screen.getByText("~42% reduce in soil loss")).toBeInTheDocument();
    expect(screen.getByText(confidenceLabel("medium", "en"))).toBeInTheDocument();
    expect(screen.getByText("17 field observations")).toBeInTheDocument();
    expect(screen.getByText("Top match")).toBeInTheDocument();
    // Evidence/How-to are hidden until /metadata reports the RAG index.
    expect(screen.queryByRole("button", { name: /Evidence/ })).toBeNull();
  });

  it("opens 'Why this?' with the (lazy-loaded) chart and the model's note", async () => {
    renderCard("en");
    const why = screen.getByRole("button", { name: /Why this\?/ });
    expect(why).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(why);
    // recharts is behind next/dynamic, so the chart arrives after a tick.
    expect(await screen.findByTestId("chart")).toBeInTheDocument();
    expect(screen.getByText("Effects are model estimates.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hide details/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("translates the practice name and the effect frame but keeps the model's number (am)", () => {
    renderCard("am");
    expect(screen.getByRole("heading", { name: "ባዮቻር + ኬሚካል ማዳበሪያ" })).toBeInTheDocument();
    const effect = screen.getByText(/~42%/);
    expect(effect.textContent).toMatch(/[ሀ-፿]/);
    // The original API sentence stays reachable for auditing.
    expect(effect).toHaveAttribute("title", expect.stringContaining("~42% reduce in soil loss"));
    expect(screen.getByText("Biochar-Inorganic Fertilizer")).toHaveAttribute("lang", "en");
  });
});
