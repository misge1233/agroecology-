"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { BookOpen, ChevronDown, HelpCircle, Sparkles, Wrench } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import type { RankedItem, RecommendResponse, RecommendationItem } from "@/lib/types";
import { confidenceLabel, confidenceMeaning, effectSentence, practiceName } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { Badge, confidenceVariant } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PracticeImage } from "@/components/practice-image";
import { EvidenceBody, HowToBody, useExplain } from "@/components/evidence-panel";
import { Skeleton } from "@/components/ui/skeleton";

// recharts (~390 KB) only ships when a reader opens "Why this?".
const PctChangeChart = dynamic(() => import("@/components/pct-chart").then((m) => m.PctChangeChart), {
  ssr: false,
  loading: () => <Skeleton className="h-56 w-full" />,
});

type Panel = "why" | "evidence" | "howto";

/**
 * One ranked practice. Every number is the model's: the effect sentence is
 * the API's own in English, and in the other languages the same pct_change
 * is placed in a translated frame (never re-estimated); the chart plots
 * details.ranked as returned.
 */
export function ResultCard({
  item,
  ranked,
  rank,
  data,
  priority,
}: {
  item: RecommendationItem;
  ranked: RankedItem | undefined;
  rank: number;
  data: RecommendResponse;
  priority?: boolean;
}) {
  const t = useTranslations("advisor.results.card");
  const locale = useLocale() as Locale;
  const { ragReady } = useExplain();
  const { load } = useExplain();
  const [open, setOpen] = useState<Panel | null>(null);
  const name = practiceName(item.practice, locale);
  const confidence = data.details.confidence;
  const effect =
    locale === "en" || !ranked
      ? item.effect
      : effectSentence(ranked.pct_change, data.query.goal_direction, data.query.indicator, locale);

  function toggle(panel: Panel) {
    setOpen((o) => (o === panel ? null : panel));
    if (panel !== "why") void load();
  }

  const panels: { key: Panel; label: string; icon: typeof HelpCircle; show: boolean }[] = [
    { key: "why", label: t("why"), icon: HelpCircle, show: true },
    { key: "evidence", label: t("evidence"), icon: BookOpen, show: ragReady },
    { key: "howto", label: t("howTo"), icon: Wrench, show: ragReady },
  ];

  return (
    <Card className={cn("overflow-hidden", rank === 1 && "border-primary/50")}>
      <article aria-labelledby={`practice-${rank}`}>
        <PracticeImage
          practice={item.practice}
          alt={t("image", { practice: name })}
          fallbackLabel={t("imageMissing")}
          title={name}
          priority={priority}
        />
        <div className="space-y-3 p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={rank === 1 ? "primary" : "neutral"} className="tabular">
              {rank === 1 ? (
                <>
                  <Sparkles className="h-3 w-3" aria-hidden /> {t("topMatch")}
                </>
              ) : (
                t("rank", { rank })
              )}
            </Badge>
            <Badge variant={confidenceVariant(confidence)}>{confidenceLabel(confidence, locale)}</Badge>
            {ranked ? (
              <span className="text-xs text-muted tabular">{t("observations", { n: ranked.n_evidence })}</span>
            ) : null}
          </div>

          <div>
            <h3 id={`practice-${rank}`} className="text-xl leading-tight sm:text-2xl">
              {name}
            </h3>
            {name !== item.practice ? (
              <p className="mt-0.5 text-xs text-muted" lang="en">
                {item.practice}
              </p>
            ) : null}
          </div>

          <p className="text-base text-text" title={locale === "en" ? undefined : t("apiEffect", { effect: item.effect })}>
            {effect}
          </p>
          <p className="text-sm text-muted">{confidenceMeaning(confidence, locale)}</p>

          <div className="flex flex-wrap gap-2 border-t border-border pt-3">
            {panels
              .filter((p) => p.show)
              .map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  aria-expanded={open === key}
                  aria-controls={`panel-${rank}-${key}`}
                  onClick={() => toggle(key)}
                  className={cn(
                    "inline-flex h-9 items-center gap-1.5 rounded-control px-3 text-sm font-medium transition-colors duration-base",
                    open === key ? "bg-primary-soft text-primary" : "text-text hover:bg-surface-2"
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {key === "why" && open === "why" ? t("hideWhy") : label}
                  <ChevronDown
                    className={cn("h-4 w-4 transition-transform duration-base", open === key && "rotate-180")}
                    aria-hidden
                  />
                </button>
              ))}
          </div>

          {open === "why" ? (
            <div id={`panel-${rank}-why`} className="space-y-3 rounded-card bg-background p-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("confidence")}</p>
                <p className="mt-1 text-sm">
                  <span className="font-semibold">{confidenceLabel(confidence, locale)}</span> —{" "}
                  {confidenceMeaning(confidence, locale)}
                </p>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("estimated")}</p>
                <PctChangeChart
                  ranked={data.details.ranked}
                  direction={data.query.goal_direction}
                  nameOf={(p) => practiceName(p, locale)}
                  highlight={item.practice}
                  changeLabel={t("change")}
                  obsOf={(n) => t("observations", { n })}
                />
                <ul className="mt-2 space-y-1">
                  {data.details.ranked.map((r) => (
                    <li key={r.practice} className="flex justify-between gap-3 text-xs">
                      <span className={cn("truncate", r.practice === item.practice ? "font-semibold text-text" : "text-muted")}>
                        {practiceName(r.practice, locale)}
                      </span>
                      <span className="shrink-0 tabular text-muted">
                        {r.pct_change > 0 ? "+" : ""}
                        {r.pct_change.toFixed(1)}% · {t("observations", { n: r.n_evidence })}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              {data.details.ranking_scope ? (
                <p className="text-xs text-muted" lang="en">
                  {data.details.ranking_scope}
                </p>
              ) : null}
              <p className="text-xs text-muted" lang="en">
                {data.details.note}
              </p>
            </div>
          ) : null}
          {open === "evidence" ? (
            <div id={`panel-${rank}-evidence`} className="rounded-card bg-background p-4">
              <EvidenceBody practice={item.practice} />
            </div>
          ) : null}
          {open === "howto" ? (
            <div id={`panel-${rank}-howto`} className="rounded-card bg-background p-4">
              <HowToBody practice={item.practice} />
            </div>
          ) : null}
        </div>
      </article>
    </Card>
  );
}
