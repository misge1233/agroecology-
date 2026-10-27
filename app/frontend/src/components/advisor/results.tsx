"use client";

import { useEffect, useState } from "react";
import { Link2, MessageSquare, RotateCcw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { postRecommend } from "@/lib/api";
import type { RecommendResponse } from "@/lib/types";
import { useApiHealth } from "@/lib/health";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { TOP_N_OPTIONS, requestKey, type AdvisorParams } from "./advisor-state";
import { ContextCard } from "./context-card";
import { RecommendationPanel } from "./recommendation-panel";

type Outcome =
  | { key: string; status: "ready"; result: RecommendResponse }
  | { key: string; status: "error"; kind: "noEvidence" | "down" | "other"; message: string };

function classify(e: unknown): { kind: "noEvidence" | "down" | "other"; message: string } {
  const message = e instanceof Error ? e.message : String(e);
  if (e instanceof TypeError) return { kind: "down", message };
  if (/no field evidence/i.test(message)) return { kind: "noEvidence", message };
  return { kind: "other", message };
}

/**
 * Scores the request in the URL. "Loading" is derived from whether the
 * stored outcome matches the current request key (F-1: no setState in the
 * effect body); the fetch is aborted when the request changes.
 */
function useRecommendation(params: AdvisorParams) {
  const key = requestKey(params);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    if (!key || params.lat == null || params.lon == null || !params.family || !params.indicator) return;
    const ctl = new AbortController();
    postRecommend(
      {
        lat: params.lat,
        lon: params.lon,
        practice_family: params.family,
        indicator: params.indicator,
        crop_type: params.crop,
        top_n: params.topN,
      },
      ctl.signal
    )
      .then((result) => setOutcome({ key, status: "ready", result }))
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setOutcome({ key, status: "error", ...classify(e) });
      });
    return () => ctl.abort();
  }, [key, params.lat, params.lon, params.family, params.indicator, params.crop, params.topN]);

  const current = key && outcome?.key === key ? outcome : null;
  return { key, loading: !!key && !current, outcome: current, retry: () => setOutcome(null) };
}

export function Results({
  params,
  onTopN,
  onReset,
}: {
  params: AdvisorParams;
  onTopN: (n: number) => void;
  onReset: () => void;
}) {
  const t = useTranslations("advisor.results");
  const tc = useTranslations("common");
  const tp = useTranslations("chat.protocol");
  const locale = useLocale() as Locale;
  const health = useApiHealth();
  const { key, loading, outcome, retry } = useRecommendation(params);

  async function share() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast({ title: t("shared"), variant: "success" });
    } catch {
      /* clipboard blocked: the address bar still carries the link */
    }
  }

  const result = outcome?.status === "ready" ? outcome.result : null;
  const explainQuery = result
    ? tp("explain", {
        lat: String(result.query.lat),
        lon: String(result.query.lon),
        crop: result.query.crop_type ? tp("growing", { crop: result.query.crop_type }) : "",
        family: result.query.practice_family,
        direction: result.query.goal_direction,
        indicator: result.query.indicator,
        practices: result.recommendations.map((r) => r.practice).join(", "),
      })
    : null;

  return (
    <section aria-labelledby="advisor-step-title" aria-busy={loading} className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="advisor-step-title" className="text-xl sm:text-2xl">
          {t("title")}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-muted">
            <span>{t("topN")}</span>
            <Select value={String(params.topN)} onValueChange={(v) => onTopN(Number(v))}>
              <SelectTrigger className="h-9 w-[7.5rem]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TOP_N_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {t("topNLabel", { n })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <Button variant="outline" size="sm" onClick={share} disabled={!result}>
            <Link2 className="h-4 w-4" aria-hidden />
            {t("share")}
          </Button>
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw className="h-4 w-4" aria-hidden />
            {t("newRequest")}
          </Button>
        </div>
      </div>

      {/* Announce results to assistive tech without re-reading the whole page. */}
      <p className="sr-only" aria-live="polite" role="status">
        {loading ? t("loading") : result ? t("live", { n: result.recommendations.length }) : ""}
      </p>

      {!key ? (
        <Card className="flex flex-col items-center justify-center p-10 text-center">
          <p className="font-semibold text-text">{t("empty.title")}</p>
          <p className="mt-1 max-w-md text-sm text-muted">{t("empty.body")}</p>
        </Card>
      ) : loading ? (
        <div className="space-y-4">
          <p className="text-sm text-muted">{t("loading")}</p>
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      ) : outcome?.status === "error" ? (
        outcome.kind === "noEvidence" ? (
          <Alert variant="info" title={t("noEvidence.title")}>
            {t("noEvidence.body")}
          </Alert>
        ) : outcome.kind === "down" || health.status === "down" ? (
          <Alert variant="danger" title={t("apiDown.title")}>
            <p>{t("apiDown.body")}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={retry}>
              {tc("retry")}
            </Button>
          </Alert>
        ) : (
          <Alert variant="danger" title={t("error.title")}>
            <p lang="en">{outcome.message}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={retry}>
              {tc("retry")}
            </Button>
          </Alert>
        )
      ) : result ? (
        <div className="space-y-5">
          <ContextCard data={result} />
          <RecommendationPanel data={result} />
          {explainQuery ? (
            <Button variant="secondary" asChild>
              <Link href={{ pathname: "/chat", query: { q: explainQuery } }} locale={locale}>
                <MessageSquare className="h-4 w-4" aria-hidden />
                {t("explainInChat")}
              </Link>
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
