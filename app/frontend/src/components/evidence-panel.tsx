"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { postExplain } from "@/lib/api";
import type { ExplainCitation, ExplainResponse, RecommendResponse } from "@/lib/types";
import { evidenceBaseSentence, studiesTooltip, type StudyLabels } from "@/lib/evidence-base";
import { aezName, practiceName, tierLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { AssistantMarkdown } from "@/components/assistant-markdown";
import { useCitations } from "@/components/citations";
import { sourceKey, uniqueSources } from "@/lib/citation-registry";
import { Badge, tierVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** Evidence-on-demand for a recommendation (P2c; two tiers P5a; evidence base P6b-i; fusion U9).
 *
 * One POST /explain per recommendation, shared by every card's Evidence and
 * How-to panels and the print sheet. U9: the answer is cached per request
 * (pin, challenge, objective, shown practices, language) for the session, the
 * explanation renders as Markdown with its markers relabelled to the page's
 * one citation registry, and How-to shows synthesised, cited steps.
 */

type FetchState =
  | { status: "idle" | "loading" }
  | { status: "ready"; result: ExplainResponse }
  | { status: "error"; message: string };

/** Session cache: one /explain per (pin, family, objective, practices, language) — D2. */
const EXPLAIN_CACHE = new Map<string, ExplainResponse>();
const MAX_CACHE = 30;

function cacheKey(data: RecommendResponse, locale: string): string {
  const q = data.query;
  return [locale, q.lat, q.lon, q.practice_family, q.indicator, q.crop_type ?? "", data.recommendations.map((r) => r.practice).join("+")].join("|");
}

const ExplainContext = createContext<{
  data: RecommendResponse;
  state: FetchState;
  /** Starts (or joins) the single POST /explain; resolves when it settles. */
  load: () => Promise<ExplainResponse | null>;
  ragReady: boolean;
  graphReady: boolean;
} | null>(null);

export function ExplainProvider({
  data,
  ragReady,
  graphReady,
  children,
}: {
  data: RecommendResponse;
  ragReady: boolean;
  graphReady: boolean;
  children: ReactNode;
}) {
  const locale = useLocale() as Locale;
  const key = cacheKey(data, locale);
  const cached = EXPLAIN_CACHE.get(key);
  const [state, setState] = useState<FetchState>(cached ? { status: "ready", result: cached } : { status: "idle" });
  const inflight = useRef<Promise<ExplainResponse | null> | null>(null);
  const load = useCallback(() => {
    const hit = EXPLAIN_CACHE.get(key);
    if (hit) {
      setState((s) => (s.status === "ready" ? s : { status: "ready", result: hit }));
      return Promise.resolve(hit);
    }
    if (inflight.current) return inflight.current;
    setState({ status: "loading" });
    inflight.current = postExplain(data, { language: locale })
      .then((result) => {
        EXPLAIN_CACHE.set(key, result);
        if (EXPLAIN_CACHE.size > MAX_CACHE) EXPLAIN_CACHE.delete(EXPLAIN_CACHE.keys().next().value as string);
        setState({ status: "ready", result });
        return result;
      })
      .catch((e: Error) => {
        setState({ status: "error", message: e.message || "" });
        return null;
      })
      .finally(() => {
        inflight.current = null;
      });
    return inflight.current;
  }, [data, locale, key]);
  return (
    <ExplainContext.Provider value={{ data, state, load, ragReady, graphReady }}>
      {children}
    </ExplainContext.Provider>
  );
}

export function useExplain() {
  const ctx = useContext(ExplainContext);
  if (!ctx) throw new Error("useExplain must be used within ExplainProvider");
  return ctx;
}

/** Same as useExplain but null outside a provider (knowledge-led results have no model). */
export function useExplainOptional() {
  return useContext(ExplainContext);
}

function StudyChip({ citation }: { citation: ExplainCitation }) {
  const t = useTranslations("evidence");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  const { label: labelOf } = useCitations();
  const isGuidance = citation.tier === "guidance";
  const ref = labelOf(citation);
  const title =
    citation.title ||
    (citation.study_no ? t("datasetStudy", { n: citation.study_no }) : isGuidance ? t("untitledDocument") : t("untitledStudy"));
  const label = [citation.era_code, title, citation.year != null ? String(citation.year) : null].filter(Boolean).join(" · ");
  const href = isGuidance
    ? (citation.url ?? (citation.doi ? `https://doi.org/${citation.doi}` : null))
    : citation.doi
      ? `https://doi.org/${citation.doi}`
      : null;
  const tier = citation.tier === "practice" ? "practice" : isGuidance ? "guidance" : "evidence";
  const body = (
    <>
      {ref ? <span className="tabular font-semibold">[{ref}]</span> : null}
      <Badge variant={tierVariant(tier)} className="px-1.5 py-0 text-[10px]">
        {tierLabel(tier, locale)}
      </Badge>
      <span className="max-w-[16rem] truncate sm:max-w-[22rem]">{label}</span>
      {citation.n_passages > 1 ? (
        <span className="shrink-0 tabular text-muted">{t("passages", { n: citation.n_passages })}</span>
      ) : null}
      {href ? (
        <>
          <ExternalLink className="h-3 w-3 shrink-0 text-muted" aria-hidden />
          <span className="sr-only">({ta("externalLink")})</span>
        </>
      ) : null}
    </>
  );
  const className =
    "inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text";
  if (!href) {
    return (
      <li className={className} title={citation.reference || citation.snippet || undefined}>
        {body}
      </li>
    );
  }
  return (
    <li className="max-w-full">
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        title={citation.reference || citation.snippet || undefined}
        className={`${className} transition-colors duration-base hover:border-primary/60`}
      >
        {body}
      </a>
    </li>
  );
}

/**
 * Sources for one practice, most relevant first (C4): those retrieved for this
 * practice, then those with passages, then the rest; within each, retrieval order.
 */
export function citationsFor(result: ExplainResponse, practice: string, tier: "evidence" | "guidance"): ExplainCitation[] {
  const all = uniqueSources(result.citations.filter((c) => (tier === "guidance") === (c.tier === "guidance")));
  const score = (c: ExplainCitation) => (c.practice === practice ? 0 : 2) + (c.n_passages > 0 ? 0 : 1);
  return all
    .map((c, i) => ({ c, i }))
    .sort((a, b) => score(a.c) - score(b.c) || a.i - b.i)
    .map(({ c }) => c);
}

const SHOWN_SOURCES = 6;

function SourceList({ items }: { items: ExplainCitation[] }) {
  const tf = useTranslations("advisor.results.card.fusion");
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, SHOWN_SOURCES);
  return (
    <>
      <ul className="flex flex-wrap gap-1.5">
        {shown.map((c, i) => (
          <StudyChip key={sourceKey(c, i)} citation={c} />
        ))}
      </ul>
      {items.length > SHOWN_SOURCES ? (
        <button type="button" className="mt-1.5 text-xs font-medium text-accent-text hover:underline" onClick={() => setAll((v) => !v)}>
          {all ? tf("fewerSources") : tf("moreSources", { n: items.length - SHOWN_SOURCES })}
        </button>
      ) : null}
    </>
  );
}

/** Loading (skeleton lines, D2) and error chrome shared by the two panels. */
function Pending({ state, load }: { state: FetchState; load: () => void }) {
  const t = useTranslations("evidence");
  const tc = useTranslations("common");
  if (state.status === "loading" || state.status === "idle") {
    return (
      <div className="space-y-2" role="status" aria-busy>
        <span className="sr-only">{t("loading")}</span>
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-10/12" />
        <Skeleton className="h-4 w-7/12" />
        <div className="flex gap-1.5 pt-1">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-32 rounded-full" />
        </div>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="space-y-2" role="alert">
        <p className="text-sm text-danger-text">{state.message || t("unavailable")}</p>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          {tc("retry")}
        </Button>
      </div>
    );
  }
  return null;
}

/** The Evidence panel body for one practice: the cited explanation and its sources. */
export function EvidenceBody({ practice }: { practice: string }) {
  const t = useTranslations("evidence");
  const tb = useTranslations("evidence.evidenceBase");
  const locale = useLocale() as Locale;
  const { state, load, graphReady } = useExplain();
  const { relabel } = useCitations();
  if (state.status !== "ready") return <Pending state={state} load={load} />;
  const { result } = state;
  const entry = result.evidence_base?.[practice];
  const studyLabels: StudyLabels = {
    untitled: t("untitledStudy"),
    fullText: tb("fullText"),
    abstractOnly: tb("abstractOnly"),
    notInCorpus: tb("notInCorpus"),
  };
  const evidence = citationsFor(result, practice, "evidence");
  const guidance = citationsFor(result, practice, "guidance");
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={result.grounded ? "primary" : "neutral"}>
          {result.grounded ? t("grounded") : t("notGrounded")}
        </Badge>
        <Badge variant="outline-neutral">{result.llm_used ? t("aiSummary") : t("deterministic")}</Badge>
      </div>
      <div data-testid="evidence-text">
        <AssistantMarkdown content={relabel(result.explanation, result.citations)} />
      </div>

      {graphReady && entry ? (
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-muted">{tb("title")}</p>
          <p className="text-sm text-muted" title={studiesTooltip(entry, studyLabels)}>
            {evidenceBaseSentence(practice, entry, tb, {
              practice: (p) => practiceName(p, locale),
              belt: (b) => aezName(b, locale),
            })}
          </p>
        </div>
      ) : null}

      {evidence.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
            {t("sourceStudies", { n: evidence.length })}
          </p>
          <SourceList items={evidence} />
        </div>
      ) : null}
      {guidance.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
            {t("guidance", { n: guidance.length })}
          </p>
          <SourceList items={guidance} />
        </div>
      ) : null}
    </div>
  );
}

/** "How to implement": synthesised, cited steps (C1) with the source text one click away. */
export function HowToBody({ practice }: { practice: string }) {
  const t = useTranslations("advisor.results.card");
  const tf = useTranslations("advisor.results.card.fusion");
  const { state, load } = useExplain();
  const { relabel } = useCitations();
  const [showSource, setShowSource] = useState(false);
  if (state.status !== "ready") return <Pending state={state} load={load} />;
  const guidance = citationsFor(state.result, practice, "guidance");
  const steps = state.result.howto?.[practice] ?? [];
  if (guidance.length === 0 && steps.length === 0) return <p className="text-sm text-muted">{t("howToEmpty")}</p>;
  return (
    <div className="space-y-3">
      {steps.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">{tf("steps")}</p>
          <ol className="list-decimal space-y-1.5 pl-5 text-sm text-text">
            {steps.map((s, i) => (
              <li key={i}>{relabel(s, state.result.citations)}</li>
            ))}
          </ol>
        </div>
      ) : null}
      {guidance.length > 0 ? <SourceList items={guidance} /> : null}
      {guidance.length > 0 ? (
        <div>
          <button
            type="button"
            className="text-xs font-medium text-accent-text hover:underline"
            aria-expanded={showSource}
            onClick={() => setShowSource((v) => !v)}
          >
            {showSource ? tf("hideSource") : tf("showSource")}
          </button>
          {showSource ? (
            <ul className="mt-2 space-y-2">
              {guidance.map((c, i) => (
                <li key={`${sourceKey(c, i)}-${i}`} className="rounded-control border border-border bg-surface p-3 text-sm text-muted">
                  {c.snippet}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
