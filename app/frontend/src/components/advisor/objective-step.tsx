"use client";

import { ArrowDown, ArrowUp, Check } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { indicatorsForFamily } from "@/lib/chat-flow";
import type { Metadata } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Chip } from "@/components/ui/chip";
import { StepFooter, StepHeader, StepPanel } from "./step-layout";

interface ObjectiveProps {
  meta: Metadata;
  family: string;
  selected: string | null;
  onSelect: (indicatorKey: string) => void;
}

/** Objective chips for one family; only indicators with evidence (Chat quick replies). */
export function ObjectiveChips({ meta, family, selected, onSelect }: ObjectiveProps) {
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

/** Advisor (U5): the same options as large tiles that also state the direction of change. */
function ObjectiveTiles({ meta, family, selected, onSelect }: ObjectiveProps) {
  const t = useTranslations("advisor.objective");
  const locale = useLocale() as Locale;
  const options = indicatorsForFamily(meta, family);
  if (options.length === 0) return <p className="text-muted">{t("none")}</p>;
  return (
    <div role="group" aria-label={t("title")} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {options.map((ind) => {
        const up = ind.direction === "increase";
        const Icon = up ? ArrowUp : ArrowDown;
        const active = selected === ind.key;
        return (
          <button
            key={ind.key}
            type="button"
            aria-pressed={active}
            onClick={() => onSelect(ind.key)}
            className={cn(
              "relative flex items-center gap-4 rounded-card border p-4 text-left transition duration-base",
              active
                ? "border-primary bg-primary-soft ring-2 ring-primary"
                : "border-border bg-surface hover:border-primary/50 hover:shadow-1"
            )}
          >
            <span
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
                active ? "bg-primary text-primary-fg" : "bg-primary-soft text-primary"
              )}
            >
              <Icon className="h-5 w-5" aria-hidden />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-text">{indicatorLabel(ind.key, locale)}</span>
              {/* Visual cue only: the label already states the direction for screen readers. */}
              <span aria-hidden className="mt-0.5 block text-sm text-muted">{up ? t("increase") : t("decrease")}</span>
            </span>
            {active ? <Check className="h-5 w-5 shrink-0 text-primary" aria-hidden /> : null}
          </button>
        );
      })}
    </div>
  );
}

export function ObjectiveStep(props: ObjectiveProps & { onBack: () => void; stepLabel: string }) {
  const t = useTranslations("advisor.objective");
  const { onBack, stepLabel, ...rest } = props;
  return (
    <StepPanel>
      <StepHeader step={stepLabel} title={t("title")} help={t("help")} />
      <ObjectiveTiles {...rest} />
      <StepFooter onBack={onBack} />
    </StepPanel>
  );
}
