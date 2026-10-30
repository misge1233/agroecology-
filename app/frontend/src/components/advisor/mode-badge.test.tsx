// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../messages/en.json";
import am from "../../../messages/am.json";
import type { ModeReason } from "@/lib/types";
import { practiceName, sourceModeLabel } from "@/i18n/glossary";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ModeBadge, ModeReasons, sourceModeOf } from "./mode-badge";

const REASONS: ModeReason[] = [
  { key: "mode.reason.thin_evidence", params: { practice: "Mulch", n_studies: 2, n_obs: 6, min_studies: 3, min_obs: 10 } },
  { key: "mode.reason.other_zones_only", params: { zone: "Dry-lowland" } },
];

function wrap(locale: "en" | "am", ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale={locale} messages={locale === "en" ? en : am}>
      <TooltipProvider>{ui}</TooltipProvider>
    </NextIntlClientProvider>
  );
}

describe("ModeBadge", () => {
  it("maps API modes to the U1 glossary modes", () => {
    expect(sourceModeOf("model-led")).toBe("model");
    expect(sourceModeOf("hybrid")).toBe("hybrid");
    expect(sourceModeOf("knowledge-led")).toBe("documented");
    expect(sourceModeOf(undefined)).toBe("model");
  });

  it("shows the glossary label for the mode and the reasons in the tooltip", async () => {
    wrap("en", <ModeBadge mode="hybrid" reasons={REASONS} />);
    const badge = screen.getByTestId("mode-badge");
    expect(badge).toHaveAttribute("data-mode", "hybrid");
    expect(badge).toHaveTextContent(sourceModeLabel("hybrid", "en"));
    fireEvent.focus(badge);
    expect(await screen.findByText(/Mulch, has only 2 studies and 6 field observations/)).toBeInTheDocument();
    expect(screen.getByText(/was measured in your moisture zone \(Dry-lowland\)/)).toBeInTheDocument();
  });

  it("renders the reasons as a list in Amharic, and never breaks on an unknown reason key", () => {
    wrap("am", <ModeReasons mode="knowledge-led" reasons={[...REASONS, { key: "mode.reason.future_reason", params: {} }]} />);
    expect(screen.getByText(am.advisor.results.mode.explain.documented)).toBeInTheDocument();
    // The practice inside a reason is localised through the glossary.
    const list = screen.getByTestId("mode-reasons");
    expect(list).toHaveTextContent(practiceName("Mulch", "am"));
    expect(list).not.toHaveTextContent(/\bMulch\b/);
    expect(screen.getByText("mode.reason.future_reason")).toBeInTheDocument();
  });
});
