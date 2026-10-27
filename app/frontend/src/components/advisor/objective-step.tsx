"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { indicatorsForFamily } from "@/lib/chat-flow";
import type { Metadata } from "@/lib/types";
import { Chip } from "@/components/ui/chip";

/** Objective chips for one family — only indicators with evidence (shared with Chat). */
export function ObjectiveChips({
  meta,
  family,
  selected,
  onSelect,
}: {
  meta: Metadata;
  family: string;
  selected: string | null;
  onSelect: (indicatorKey: string) => void;
}) {
  const t = useTranslations("advisor.objective");
  const locale = useLocale() as Locale;
  const options = indicatorsForFamily(meta, family);
  if (options.length === 0) return <p className="text-sm text-muted">{t("none")}</p>;
  return (
    <div role="group" aria-label={t("title")} className="flex flex-wrap gap-2">
      {options.map((ind) => {
        const Icon = ind.direction === "increase" ? ArrowUp : ArrowDown;
        return (
          <Chip
            key={ind.key}
            selected={selected === ind.key}
            onClick={() => onSelect(ind.key)}
            icon={<Icon className="h-4 w-4 text-primary" aria-hidden />}
          >
            {indicatorLabel(ind.key, locale)}
          </Chip>
        );
      })}
    </div>
  );
}

export function ObjectiveStep(props: {
  meta: Metadata;
  family: string;
  selected: string | null;
  onSelect: (indicatorKey: string) => void;
}) {
  const t = useTranslations("advisor.objective");
  return (
    <div className="space-y-5">
      <div>
        <h2 id="advisor-step-title" className="text-xl sm:text-2xl">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("help")}</p>
      </div>
      <ObjectiveChips {...props} />
    </div>
  );
}
