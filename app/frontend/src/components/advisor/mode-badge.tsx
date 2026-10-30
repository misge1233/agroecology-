"use client";

import { Info } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { practiceName, sourceModeLabel, sourceModeTooltip, type SourceMode } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import type { AdvisoryMode, ModeReason } from "@/lib/types";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** API mode → glossary key (U1 reserved "hybrid" / "documented" for exactly this). */
export function sourceModeOf(mode: AdvisoryMode | undefined | null): SourceMode {
  if (mode === "hybrid") return "hybrid";
  if (mode === "knowledge-led") return "documented";
  return "model";
}

const VARIANT: Record<SourceMode, BadgeProps["variant"]> = {
  model: "outline-primary",
  hybrid: "outline-accent",
  documented: "outline-secondary",
};

/** Render one mode reason (catalog key + params) in the UI language. */
export function useReasonText() {
  const t = useTranslations("advisor.results.mode.reason");
  const locale = useLocale() as Locale;
  return (reason: ModeReason): string => {
    const key = reason.key.replace(/^mode\.reason\./, "");
    // A reason the catalog does not know yet (a newer backend) is shown by its
    // key rather than as a next-intl "missing message" string.
    if (!t.has(key as never)) return reason.key;
    const params = Object.fromEntries(
      Object.entries(reason.params ?? {}).map(([k, v]) => [k, k === "practice" && typeof v === "string" ? practiceName(v, locale) : v])
    );
    return t(key as never, params as never);
  };
}

/**
 * The source badge (U1) now driven by the advisory mode (P9): the label is
 * the glossary's, the tooltip explains the mode and lists the reasons.
 */
export function ModeBadge({ mode, reasons = [] }: { mode: AdvisoryMode; reasons?: ModeReason[] }) {
  const t = useTranslations("advisor.results");
  const locale = useLocale() as Locale;
  const reasonText = useReasonText();
  const sm = sourceModeOf(mode);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-full"
          aria-label={`${t("source.label")}: ${sourceModeLabel(sm, locale)}`}
          data-testid="mode-badge"
          data-mode={mode}
        >
          <Badge variant={VARIANT[sm]}>{sourceModeLabel(sm, locale)}</Badge>
          <Info className="h-3.5 w-3.5 text-muted" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">
        <p>{sourceModeTooltip(sm, locale)}</p>
        {reasons.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted">
            {reasons.map((r, i) => (
              <li key={`${r.key}-${i}`}>{reasonText(r)}</li>
            ))}
          </ul>
        ) : null}
      </TooltipContent>
    </Tooltip>
  );
}

/** The reasons as plain text under a heading (results view and print sheet). */
export function ModeReasons({ mode, reasons }: { mode: AdvisoryMode; reasons: ModeReason[] }) {
  const t = useTranslations("advisor.results.mode");
  const locale = useLocale() as Locale;
  const reasonText = useReasonText();
  if (reasons.length === 0) return null;
  return (
    <div className="rounded-card border border-border bg-surface-2 p-3 text-sm" data-testid="mode-reasons">
      <p className="font-medium text-text">{t(`explain.${sourceModeOf(mode)}`)}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
        {reasons.map((r, i) => (
          <li key={`${r.key}-${i}`}>{reasonText(r)}</li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-muted">{sourceModeTooltip(sourceModeOf(mode), locale)}</p>
    </div>
  );
}
