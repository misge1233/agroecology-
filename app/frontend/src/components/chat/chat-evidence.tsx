"use client";

import { ArrowRight, FileText, ListOrdered } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { confidenceLabel, effectSentence, practiceName } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { advisorQuery } from "@/lib/chat-protocol";
import type { AdvisoryEvent, RecommendQuery, RecommendResponse } from "@/lib/types";
import { Badge, confidenceVariant } from "@/components/ui/badge";
import { ModeBadge } from "@/components/advisor/mode-badge";

const TOP_N = 3;

/**
 * The evidence behind one chat answer (U6, conversational chat): a compact
 * attachment under the assistant's words, never a form. Every number is the
 * model's own (the effect sentence is the API's in English and the same
 * pct_change in a translated frame otherwise); documented practices are
 * named without any effect. The full analysis is one link away in the Advisor.
 */
export function ChatEvidence({
  recommendation,
  advisory,
  advisoryQuery,
}: {
  recommendation: RecommendResponse | null;
  advisory: AdvisoryEvent | null;
  advisoryQuery: RecommendQuery | null;
}) {
  const t = useTranslations("chat.evidence");
  const tc = useTranslations("chat");
  const locale = useLocale() as Locale;
  const query = recommendation?.query ?? advisoryQuery;
  const documented = advisory?.knowledge_candidates ?? [];

  const advisorLink = query ? (
    <Link
      href={{ pathname: "/advisor", query: advisorQuery(query, TOP_N) }}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
    >
      {tc("openInAdvisor")}
      <ArrowRight className="h-4 w-4" aria-hidden />
    </Link>
  ) : null;

  if (!recommendation) {
    if (advisory?.mode !== "knowledge-led") return null;
    // Knowledge-led: the reply text already lists the documented practices.
    return (
      <div data-testid="chat-knowledge-led" className="flex flex-wrap items-center gap-3 pl-1">
        <ModeBadge mode="knowledge-led" reasons={advisory.reasons} />
        <span className="text-xs text-muted">{tc("advisory.knowledgeLed")}</span>
        {advisorLink}
      </div>
    );
  }

  const confidence = recommendation.details.confidence;
  return (
    <section
      data-testid="chat-recommendation"
      aria-label={t("title")}
      className="overflow-hidden rounded-card border border-border bg-surface shadow-1"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface-2 px-4 py-2.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-text">
          <ListOrdered className="h-4 w-4 text-primary" aria-hidden />
          {t("title")}
        </p>
        <div className="flex items-center gap-2">
          {advisory ? <ModeBadge mode={advisory.mode} reasons={advisory.reasons} /> : null}
          <Badge variant={confidenceVariant(confidence)}>{confidenceLabel(confidence, locale)}</Badge>
        </div>
      </header>
      <ol className="divide-y divide-border">
        {recommendation.recommendations.map((item, i) => {
          const ranked = recommendation.details.ranked.find((r) => r.practice === item.practice);
          const effect =
            locale === "en" || !ranked
              ? item.effect
              : effectSentence(ranked.pct_change, recommendation.query.goal_direction, recommendation.query.indicator, locale);
          return (
            <li key={item.practice} className="flex items-start gap-3 px-4 py-3">
              <span
                aria-hidden
                className={
                  i === 0
                    ? "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold tabular text-primary-fg"
                    : "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold tabular text-muted ring-1 ring-border"
                }
              >
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="font-semibold text-text">{practiceName(item.practice, locale)}</p>
                <p className="text-sm text-muted">
                  {effect}
                  {ranked ? <span className="tabular"> · {t("observations", { n: ranked.n_evidence })}</span> : null}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
      {advisory?.mode === "hybrid" && documented.length > 0 ? (
        <p data-testid="chat-documented" className="flex items-start gap-2 border-t border-border px-4 py-2.5 text-xs text-muted">
          <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{t("alsoDocumented", { names: documented.map((c) => c.label).join(", ") })}</span>
        </p>
      ) : null}
      {advisorLink ? <footer className="border-t border-border px-4 py-2.5">{advisorLink}</footer> : null}
    </section>
  );
}
