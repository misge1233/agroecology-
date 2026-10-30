"use client";

import { useState } from "react";
import { BookOpen, ExternalLink, FileText, Landmark } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { COMPONENTS, indicatorLabel, practiceName, tierLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import type { KnowledgeCandidate, KnowledgeCitation, KnowledgeSource } from "@/lib/types";
import { Badge, tierVariant } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

const SOURCE_ICON: Record<KnowledgeSource, typeof BookOpen> = {
  evidence_other_objectives: BookOpen,
  documented_in_guidance: FileText,
  documented_practice_record: Landmark,
};
const SOURCE_TIER: Record<KnowledgeSource, "evidence" | "guidance" | "practice"> = {
  evidence_other_objectives: "evidence",
  documented_in_guidance: "guidance",
  documented_practice_record: "practice",
};

/** Localised display label of a candidate (component via the glossary; records by title). */
export function candidateLabel(c: KnowledgeCandidate, locale: Locale): string {
  if (c.component && COMPONENTS[c.component]) return COMPONENTS[c.component][locale] ?? COMPONENTS[c.component].en;
  return c.label;
}

/** "T0001 · Title · 2019", or "Dataset study #123" for a study outside the ERA corpus. */
export function citationLabel(c: KnowledgeCitation, t: (key: never, values?: never) => string): string {
  const code = c.era_code ?? (c.study_no != null && !c.title ? t("datasetStudy" as never, { n: String(c.study_no) } as never) : null);
  const title = c.title || (code ? null : c.tier === "evidence" ? t("untitledStudy" as never) : t("untitledDocument" as never));
  return [code, title, c.year != null ? String(c.year) : null].filter(Boolean).join(" · ");
}

function Citation({ c }: { c: KnowledgeCitation }) {
  const t = useTranslations("evidence");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  const label = citationLabel(c, t);
  const href = c.url ?? (c.doi ? `https://doi.org/${c.doi}` : null);
  const body = (
    <>
      {c.ref ? <span className="tabular font-semibold">[{c.ref}]</span> : null}
      <Badge variant={tierVariant(c.tier)} className="px-1.5 py-0 text-[10px]">
        {tierLabel(c.tier, locale)}
      </Badge>
      <span className="max-w-[16rem] truncate sm:max-w-[22rem]">{label}</span>
      {href ? (
        <>
          <ExternalLink className="h-3 w-3 shrink-0 text-muted" aria-hidden />
          <span className="sr-only">({ta("externalLink")})</span>
        </>
      ) : null}
    </>
  );
  const cls = "inline-flex max-w-full items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-text";
  return href ? (
    <li className="max-w-full">
      <a href={href} target="_blank" rel="noopener noreferrer" title={c.snippet ?? undefined} className={`${cls} hover:border-secondary`}>
        {body}
      </a>
    </li>
  ) : (
    <li className={cls} title={c.snippet ?? undefined}>
      {body}
    </li>
  );
}

const VISIBLE_CITATIONS = 6;

/** The citation chips of one card; long lists fold behind "Show all (n)". */
function CitationList({ citations }: { citations: KnowledgeCitation[] }) {
  const t = useTranslations("advisor.results.documented");
  const [open, setOpen] = useState(false);
  const shown = open ? citations : citations.slice(0, VISIBLE_CITATIONS);
  return (
    <div className="mt-3">
      <ul className="flex flex-wrap gap-1.5" aria-label={t("sources.label")}>
        {shown.map((cit, k) => (
          <Citation key={`${cit.ref ?? k}-${cit.era_code ?? cit.url ?? cit.title ?? k}`} c={cit} />
        ))}
      </ul>
      {citations.length > VISIBLE_CITATIONS ? (
        <button
          type="button"
          className="mt-1.5 text-xs font-medium text-secondary-text underline-offset-2 hover:underline"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? t("sources.showFewer") : t("sources.showAll", { n: citations.length })}
        </button>
      ) : null}
    </div>
  );
}

/**
 * "Documented practices" (P9): the knowledge candidates of a hybrid or
 * knowledge-led advisory. Secondary-outline styling, never an effect number
 * — each card lists its sources, its support counts, the frozen practices it
 * maps to and the backend's deterministic "why this is suggested" line.
 */
export function KnowledgeCandidates({
  candidates,
  mode,
  compact = false,
}: {
  candidates: KnowledgeCandidate[];
  mode: "hybrid" | "knowledge-led";
  compact?: boolean;
}) {
  const t = useTranslations("advisor.results.documented");
  const locale = useLocale() as Locale;
  if (candidates.length === 0) {
    return (
      <Card className="border-secondary/50 p-4" data-testid="documented-practices">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary-text">{t("title")}</p>
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      </Card>
    );
  }
  return (
    <section aria-labelledby="documented-title" data-testid="documented-practices" className="space-y-3">
      <div>
        <h3 id="documented-title" className="text-xs font-semibold uppercase tracking-[0.14em] text-secondary-text">
          {t("title")}
        </h3>
        <p className="mt-1 text-sm text-muted">{mode === "hybrid" ? t("introHybrid") : t("introKnowledge")}</p>
      </div>
      <ol className={compact ? "space-y-2" : "space-y-3"}>
        {candidates.map((c, i) => (
          <li key={c.key}>
            <Card className="border-secondary/50 p-4" data-testid="documented-card">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline-secondary" className="tabular">
                  {t("rank", { rank: i + 1 })}
                </Badge>
                {c.sources.map((s) => {
                  const Icon = SOURCE_ICON[s];
                  return (
                    <Badge key={s} variant={tierVariant(SOURCE_TIER[s])} className="gap-1">
                      <Icon className="h-3 w-3" aria-hidden />
                      {t(`source.${s}`)}
                    </Badge>
                  );
                })}
              </div>
              <h4 className="mt-2 text-lg leading-tight">{candidateLabel(c, locale)}</h4>
              {c.component && candidateLabel(c, locale) !== c.component ? (
                <p className="text-xs text-muted" lang="en">
                  {c.component}
                </p>
              ) : null}
              <p className="mt-2 text-sm text-text" data-testid="candidate-rationale">
                <span className="font-medium">{t("why")}: </span>
                {c.rationale_text}
              </p>
              <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                <div>
                  <dt className="inline">{t("support.documents")}: </dt>
                  <dd className="inline tabular">{c.support.n_documents}</dd>
                </div>
                {c.support.n_passages > 0 ? (
                  <div>
                    <dt className="inline">{t("support.passages")}: </dt>
                    <dd className="inline tabular">{c.support.n_passages}</dd>
                  </div>
                ) : null}
                {Object.keys(c.support.other_objectives).length > 0 ? (
                  <div>
                    <dt className="inline">{t("support.otherObjectives")}: </dt>
                    <dd className="inline">
                      {Object.entries(c.support.other_objectives)
                        .map(([k, n]) => `${indicatorLabel(k, locale)} (${n})`)
                        .join(", ")}
                    </dd>
                  </div>
                ) : null}
              </dl>
              {c.practices.length > 0 ? (
                <p className="mt-2 text-xs text-muted">
                  {t("mapsTo")}: {c.practices.map((p) => practiceName(p, locale)).join(" · ")}
                </p>
              ) : null}
              {!compact ? <CitationList citations={c.citations} /> : null}
            </Card>
          </li>
        ))}
      </ol>
      <p className="text-xs italic text-muted">{t("disclaimer")}</p>
    </section>
  );
}
