"use client";

import { useEffect, useState } from "react";
import { FileDown, Link2, MessageSquare, RotateCcw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { postAdvise } from "@/lib/api";
import type { AdviseResponse } from "@/lib/types";
import { useApiHealth } from "@/lib/health";
import { useMetadata } from "@/components/metadata-provider";
import { ExplainProvider, useExplainOptional } from "@/components/evidence-panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { TOP_N_OPTIONS, requestKey, type AdvisorParams } from "./advisor-state";
import { ContextCard } from "./context-card";
import { KnowledgeCandidates } from "./knowledge-candidates";
import { ModeBadge, ModeReasons } from "./mode-badge";
import { PrintSheet } from "./print-sheet";
import { RecommendationPanel } from "./recommendation-panel";

/** "Save as PDF": make sure the evidence is loaded, then hand over to the browser. */
function SavePdfButton() {
  const tp = useTranslations("advisor.results.print");
  const explain = useExplainOptional();
  const [preparing, setPreparing] = useState(false);
  async function onPrint() {
    setPreparing(true);
    try {
      if (explain?.ragReady) await explain.load();
      // Let React commit the evidence into the print sheet before the dialog opens.
      await new Promise((r) => setTimeout(r, 120));
      window.print();
    } finally {
      setPreparing(false);
    }
  }
  return (
    <Button variant="outline" size="sm" onClick={() => void onPrint()} loading={preparing}>
      {!preparing ? <FileDown className="h-4 w-4" aria-hidden /> : null}
      {preparing ? tp("preparing") : tp("savePdf")}
    </Button>
  );
}

type Outcome =
  | { key: string; status: "ready"; advisory: AdviseResponse }
  | { key: string; status: "error"; kind: "down" | "other"; message: string };

function classify(e: unknown): { kind: "down" | "other"; message: string } {
  const message = e instanceof Error ? e.message : String(e);
  if (e instanceof TypeError) return { kind: "down", message };
  return { kind: "other", message };
}

/**
 * Asks the advisory for the request in the URL (P9: /advise wraps /recommend
 * with the evidence mode and the documented practices). "Loading" is derived
 * from whether the stored outcome matches the current request key (F-1: no
 * setState in the effect body); the fetch is aborted when the request changes.
 */
function useAdvisory(params: AdvisorParams, language: Locale) {
  const key = requestKey(params) ? `${requestKey(params)}|${language}` : null;
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    if (!key || params.lat == null || params.lon == null || !params.family || !params.indicator) return;
    const ctl = new AbortController();
    postAdvise(
      {
        lat: params.lat,
        lon: params.lon,
        practice_family: params.family,
        indicator: params.indicator,
        crop_type: params.crop,
        top_n: params.topN,
        language,
      },
      ctl.signal
    )
      .then((advisory) => setOutcome({ key, status: "ready", advisory }))
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setOutcome({ key, status: "error", ...classify(e) });
      });
    return () => ctl.abort();
  }, [key, params.lat, params.lon, params.family, params.indicator, params.crop, params.topN, language]);

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
  const { meta } = useMetadata();
  const { key, loading, outcome, retry } = useAdvisory(params, locale);

  async function share() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast({ title: t("shared"), variant: "success" });
    } catch {
      /* clipboard blocked: the address bar still carries the link */
    }
  }

  const advisory = outcome?.status === "ready" ? outcome.advisory : null;
  const result = advisory?.model ?? null;
  const mode = advisory?.mode ?? "model-led";
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

  const body = (
    <section aria-labelledby="advisor-step-title" aria-busy={loading} className="space-y-5">
      <div className="no-print flex flex-wrap items-end justify-between gap-3">
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
          {advisory ? <SavePdfButton /> : null}
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw className="h-4 w-4" aria-hidden />
            {t("newRequest")}
          </Button>
        </div>
      </div>

      {/* Announce results to assistive tech without re-reading the whole page. */}
      <p className="no-print sr-only" aria-live="polite" role="status">
        {loading
          ? t("loading")
          : result
            ? t("live", { n: result.recommendations.length })
            : advisory
              ? t("liveDocumented", { n: advisory.knowledge_candidates.length })
              : ""}
      </p>

      {!key ? (
        <Card className="no-print flex flex-col items-center justify-center p-10 text-center">
          <p className="font-semibold text-text">{t("empty.title")}</p>
          <p className="mt-1 max-w-md text-sm text-muted">{t("empty.body")}</p>
        </Card>
      ) : loading ? (
        <div className="no-print space-y-4">
          <p className="text-sm text-muted">{t("loading")}</p>
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      ) : outcome?.status === "error" ? (
        outcome.kind === "down" || health.status === "down" ? (
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
      ) : advisory && result ? (
        <>
          <div className="no-print space-y-5">
            <ContextCard data={result} />
            {mode !== "model-led" ? <ModeReasons mode={mode} reasons={advisory.reasons} /> : null}
            <RecommendationPanel data={result} withProvider={false} mode={mode} reasons={advisory.reasons} />
            {mode === "hybrid" ? <KnowledgeCandidates candidates={advisory.knowledge_candidates} mode="hybrid" /> : null}
            {explainQuery ? (
              <Button variant="secondary" asChild>
                <Link href={{ pathname: "/chat", query: { q: explainQuery } }} locale={locale}>
                  <MessageSquare className="h-4 w-4" aria-hidden />
                  {t("explainInChat")}
                </Link>
              </Button>
            ) : null}
          </div>
          <PrintSheet data={result} advisory={advisory} />
        </>
      ) : advisory ? (
        // Knowledge-led (P9): replaces the former "no field evidence" error state.
        <>
          <div className="no-print space-y-5" data-testid="knowledge-led">
            <Alert variant="info" title={t("knowledgeLed.title")}>
              <p>{t("knowledgeLed.body")}</p>
              <div className="mt-2 flex items-center gap-2">
                <ModeBadge mode="knowledge-led" reasons={advisory.reasons} />
              </div>
            </Alert>
            {Object.keys(advisory.context ?? {}).length > 0 ? (
              <ContextCard
                data={{
                  query: { lat: params.lat ?? 0, lon: params.lon ?? 0, practice_family: params.family ?? "", indicator: params.indicator ?? "", goal_direction: "" },
                  recommendations: [],
                  details: { context: advisory.context, crop_group: null, confidence: "low", ranked: [], n_candidates: 0, note: "" },
                }}
              />
            ) : null}
            <ModeReasons mode="knowledge-led" reasons={advisory.reasons} />
            <KnowledgeCandidates candidates={advisory.knowledge_candidates} mode="knowledge-led" />
          </div>
          <PrintSheet data={null} advisory={advisory} params={params} />
        </>
      ) : null}
    </section>
  );
  // One /explain per result, shared by the cards' Evidence/How-to panels and the print sheet.
  if (!result) return body;
  return (
    <ExplainProvider data={result} ragReady={!!meta?.rag_ready} graphReady={!!meta?.graph_ready}>
      {body}
    </ExplainProvider>
  );
}
