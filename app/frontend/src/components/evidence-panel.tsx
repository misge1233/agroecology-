"use client";

import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { postExplain } from "@/lib/api";
import type { ExplainCitation, ExplainResponse, RecommendResponse } from "@/lib/types";
import { evidenceBaseSentence, studiesTooltip, type StudyLabels } from "@/lib/evidence-base";
import { aezName, practiceName, tierLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { Badge, tierVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/** Evidence-on-demand for a recommendation (P2c; two-tier P5a; evidence base P6b-i).
 *
 * U1 lifts the single POST /explain behind a context so every card of one
 * recommendation shares it (the Evidence and How-to panels both read it) and
 * localises every label; the explanation itself is written by the backend in
 * the UI language (`language` on the request). Counts and provenance only —
 * effect magnitudes belong to the model and are never shown here.
 */

type FetchState =
  | { status: "idle" | "loading" }
  | { status: "ready"; result: ExplainResponse }
  | { status: "error"; message: string };

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
  const [state, setState] = useState<FetchState>({ status: "idle" });
  const inflight = useRef<Promise<ExplainResponse | null> | null>(null);
  const settled = useRef<ExplainResponse | null>(null);
  const load = useCallback(() => {
    if (settled.current) return Promise.resolve(settled.current);
    if (inflight.current) return inflight.current;
    setState({ status: "loading" });
    inflight.current = postExplain(data, { language: locale })
      .then((result) => {
        settled.current = result;
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
  }, [data, locale]);
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

function StudyChip({ citation }: { citation: ExplainCitation }) {
  const t = useTranslations("evidence");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  const isGuidance = citation.tier === "guidance";
  const label = [
    citation.era_code,
    citation.title || (isGuidance ? t("untitledDocument") : t("untitledStudy")),
    citation.year != null ? String(citation.year) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const href = isGuidance
    ? (citation.url ?? (citation.doi ? `https://doi.org/${citation.doi}` : null))
    : citation.doi
      ? `https://doi.org/${citation.doi}`
      : null;
  const body = (
    <>
      <Badge variant={tierVariant(isGuidance ? "guidance" : "evidence")} className="px-1.5 py-0 text-[10px]">
        {tierLabel(isGuidance ? "guidance" : "evidence", locale)}
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
      <li className={className} title={citation.snippet}>
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
        title={citation.snippet}
        className={`${className} transition-colors duration-base hover:border-primary/60`}
      >
        {body}
      </a>
    </li>
  );
}

function citationsFor(result: ExplainResponse, practice: string, tier: "evidence" | "guidance") {
  const all = result.citations.filter((c) => (tier === "guidance") === (c.tier === "guidance"));
  const mine = all.filter((c) => c.practice === practice);
  return mine.length > 0 ? mine : all;
}

/** Shared loading/error chrome for the two panels. */
function Pending({ state, load }: { state: FetchState; load: () => void }) {
  const t = useTranslations("evidence");
  const tc = useTranslations("common");
  if (state.status === "loading" || state.status === "idle") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        {t("loading")}
      </p>
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

/** The Evidence panel body for one practice. */
export function EvidenceBody({ practice }: { practice: string }) {
  const t = useTranslations("evidence");
  const tb = useTranslations("evidence.evidenceBase");
  const locale = useLocale() as Locale;
  const { state, load, graphReady } = useExplain();
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
      <p className="whitespace-pre-line text-sm leading-relaxed text-text">{result.explanation}</p>

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
          <ul className="flex flex-wrap gap-1.5">
            {evidence.map((c, i) => (
              <StudyChip key={c.era_code ?? c.doi ?? c.title ?? i} citation={c} />
            ))}
          </ul>
        </div>
      ) : null}
      {guidance.length > 0 ? (
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
            {t("guidance", { n: guidance.length })}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {guidance.map((c, i) => (
              <StudyChip key={c.url ?? c.doi ?? c.title ?? i} citation={c} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** "How to implement": the guidance documents (GARDIAN) behind one practice. */
export function HowToBody({ practice }: { practice: string }) {
  const t = useTranslations("advisor.results.card");
  const { state, load } = useExplain();
  if (state.status !== "ready") return <Pending state={state} load={load} />;
  const guidance = citationsFor(state.result, practice, "guidance");
  if (guidance.length === 0) return <p className="text-sm text-muted">{t("howToEmpty")}</p>;
  return (
    <ul className="space-y-2">
      {guidance.map((c, i) => (
        <li key={c.url ?? c.doi ?? c.title ?? i} className="rounded-control border border-border bg-surface p-3">
          <ul className="flex flex-wrap gap-1.5">
            <StudyChip citation={c} />
          </ul>
          <p className="mt-2 text-sm text-muted">{c.snippet}</p>
        </li>
      ))}
    </ul>
  );
}
