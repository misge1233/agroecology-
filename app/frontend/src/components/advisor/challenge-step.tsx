"use client";

import { useLocale, useTranslations } from "next-intl";
import { familyBlurb, familyShort } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { cn } from "@/lib/utils";
import { FAMILY_ICONS } from "./family-icons";

/** The five challenge families as pressable cards (shared with Chat). */
export function ChallengeCards({
  families,
  selected,
  onSelect,
  className,
}: {
  families: string[];
  selected: string | null;
  onSelect: (family: string) => void;
  className?: string;
}) {
  const t = useTranslations("advisor.challenge");
  const locale = useLocale() as Locale;
  return (
    <div role="group" aria-label={t("title")} className={cn("grid gap-3 sm:grid-cols-2", className)}>
      {families.map((family) => {
        const Icon = FAMILY_ICONS[family] ?? FAMILY_ICONS["Crop production and management"];
        const active = selected === family;
        return (
          <button
            key={family}
            type="button"
            aria-pressed={active}
            onClick={() => onSelect(family)}
            className={cn(
              "flex items-start gap-3 rounded-card border p-4 text-left transition-colors duration-base",
              active
                ? "border-primary bg-primary-soft"
                : "border-border bg-surface hover:border-primary/50 hover:bg-surface-2"
            )}
          >
            <span
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-control",
                active ? "bg-primary text-primary-fg" : "bg-primary-soft text-primary"
              )}
            >
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold text-text">{familyShort(family, locale)}</span>
              <span className="mt-0.5 block text-sm text-muted">{familyBlurb(family, locale)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function ChallengeStep({
  families,
  selected,
  onSelect,
}: {
  families: string[];
  selected: string | null;
  onSelect: (family: string) => void;
}) {
  const t = useTranslations("advisor.challenge");
  return (
    <div className="space-y-5">
      <div>
        <h2 id="advisor-step-title" className="text-xl sm:text-2xl">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("help")}</p>
      </div>
      <ChallengeCards families={families} selected={selected} onSelect={onSelect} />
    </div>
  );
}
