"use client";

import Image from "next/image";
import { Check } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { familyBlurb, familyShort } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { cn } from "@/lib/utils";
import { FAMILY_ICONS, FAMILY_IMAGES } from "./family-icons";
import { StepFooter, StepHeader, StepPanel } from "./step-layout";

/**
 * The five challenge families as pressable cards (shared with Chat).
 * `photo` (Advisor, U5) adds the family photo above the text.
 */
export function ChallengeCards({
  families,
  selected,
  onSelect,
  className,
  photo = false,
}: {
  families: string[];
  selected: string | null;
  onSelect: (family: string) => void;
  className?: string;
  photo?: boolean;
}) {
  const t = useTranslations("advisor.challenge");
  const locale = useLocale() as Locale;
  return (
    <div
      role="group"
      aria-label={t("title")}
      className={cn("grid gap-4", photo ? "sm:grid-cols-2 lg:grid-cols-3" : "gap-3 sm:grid-cols-2", className)}
    >
      {families.map((family) => {
        const Icon = FAMILY_ICONS[family] ?? FAMILY_ICONS["Crop production and management"];
        const image = photo ? FAMILY_IMAGES[family] : undefined;
        const active = selected === family;
        return (
          <button
            key={family}
            type="button"
            aria-pressed={active}
            onClick={() => onSelect(family)}
            className={cn(
              "group relative overflow-hidden rounded-card border text-left transition duration-base",
              photo ? "flex flex-col bg-surface hover:-translate-y-0.5 hover:shadow-2" : "flex items-start gap-3 p-4",
              active
                ? "border-primary bg-primary-soft ring-2 ring-primary"
                : "border-border bg-surface hover:border-primary/50"
            )}
          >
            {image ? (
              <span className="relative block aspect-[16/9] w-full overflow-hidden bg-surface-2">
                <Image
                  src={image}
                  alt=""
                  fill
                  sizes="(min-width: 1024px) 26vw, (min-width: 640px) 45vw, 100vw"
                  className="object-cover transition-transform duration-base group-hover:scale-[1.03]"
                />
              </span>
            ) : null}
            {active ? (
              <span
                aria-hidden
                className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-fg shadow-1"
              >
                <Check className="h-4 w-4" />
              </span>
            ) : null}
            <span className={cn("flex min-w-0 items-start gap-3", photo ? "p-5" : null)}>
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
                <span className="mt-1 block text-sm leading-relaxed text-muted">{familyBlurb(family, locale)}</span>
              </span>
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
  onBack,
  stepLabel,
}: {
  families: string[];
  selected: string | null;
  onSelect: (family: string) => void;
  onBack: () => void;
  stepLabel: string;
}) {
  const t = useTranslations("advisor.challenge");
  return (
    <StepPanel>
      <StepHeader step={stepLabel} title={t("title")} help={t("help")} />
      <ChallengeCards families={families} selected={selected} onSelect={onSelect} photo />
      <StepFooter onBack={onBack} />
    </StepPanel>
  );
}
