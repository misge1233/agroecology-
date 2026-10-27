"use client";

import { useLocale, useTranslations } from "next-intl";
import { familyShort } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import type { RecommendResponse } from "@/lib/types";
import { useMetadata } from "@/components/metadata-provider";
import { ExplainProvider } from "@/components/evidence-panel";
import { ResultCard } from "./result-card";
import { SourceBadge } from "./source-badge";

/** The ranked list for one response — used by the Advisor results and by Chat. */
export function RecommendationPanel({ data, children }: { data: RecommendResponse; children?: React.ReactNode }) {
  const t = useTranslations("advisor.results");
  const locale = useLocale() as Locale;
  const { meta } = useMetadata();
  const byPractice = new Map(data.details.ranked.map((r) => [r.practice, r]));
  return (
    <ExplainProvider data={data} ragReady={!!meta?.rag_ready} graphReady={!!meta?.graph_ready}>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted">
            {t("rankedWithin", { family: familyShort(data.query.practice_family, locale) })}
            {data.details.n_grounded != null ? (
              <>
                {" · "}
                {t("withEvidence", { grounded: data.details.n_grounded, candidates: data.details.n_candidates })}
              </>
            ) : null}
          </p>
          <SourceBadge mode="model" />
        </div>
        {children}
        <ol className="space-y-4">
          {data.recommendations.map((item, i) => (
            <li key={item.practice}>
              <ResultCard item={item} ranked={byPractice.get(item.practice)} rank={i + 1} data={data} priority={i === 0} />
            </li>
          ))}
        </ol>
        <p className="text-xs italic text-muted">{t("disclaimer")}</p>
      </div>
    </ExplainProvider>
  );
}
