"use client";

import { Info } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { sourceModeLabel, sourceModeTooltip, type SourceMode } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Where a ranking comes from. U1 ships "Field-trial model" only; "Hybrid"
 * and "Documented practice" are reserved for P9 (WOCAT) and never shown yet.
 */
export function SourceBadge({ mode = "model" }: { mode?: SourceMode }) {
  const t = useTranslations("advisor.results.source");
  const locale = useLocale() as Locale;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-full"
          aria-label={`${t("label")}: ${sourceModeLabel(mode, locale)}`}
        >
          <Badge variant="outline-primary">{sourceModeLabel(mode, locale)}</Badge>
          <Info className="h-3.5 w-3.5 text-muted" aria-hidden />
        </button>
      </TooltipTrigger>
      <TooltipContent>{sourceModeTooltip(mode, locale)}</TooltipContent>
    </Tooltip>
  );
}
