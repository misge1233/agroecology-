"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import type { AdviseResponse, RecommendResponse } from "@/lib/types";
import { evidenceBaseSentence } from "@/lib/evidence-base";
import { useClientValue } from "@/lib/client-value";
import {
  aezName,
  confidenceLabel,
  confidenceMeaning,
  effectSentence,
  familyName,
  indicatorLabel,
  practiceName,
  sourceModeLabel,
  sourceModeTooltip,
  tierLabel,
} from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { useExplainOptional } from "@/components/evidence-panel";
import type { AdvisorParams } from "./advisor-state";
import { candidateLabel, citationLabel } from "./knowledge-candidates";
import { sourceModeOf, useReasonText } from "./mode-badge";

const CONTEXT_FIELDS: { key: string; k: string; unit: "mm" | "m" | "percent" | "days" | "celsius" | null; digits: number }[] = [
  { key: "Rainfall", k: "rainfall", unit: "mm", digits: 0 },
  { key: "temp_mean_annual", k: "temp", unit: "celsius", digits: 1 },
  { key: "Altitude_r", k: "altitude", unit: "m", digits: 0 },
  { key: "slope", k: "slope", unit: "percent", digits: 1 },
  { key: "soil_clay", k: "clay", unit: "percent", digits: 0 },
  { key: "soil_ph", k: "ph", unit: null, digits: 1 },
  { key: "soil_soc", k: "soc", unit: null, digits: 1 },
  { key: "lgp_days", k: "lgp", unit: "days", digits: 0 },
];

/**
 * The printable advisory (U2 item 2, extended in P9). Hidden on screen
 * (`print-only`), it is what "Save as PDF" / Ctrl+P produce: the request, the
 * context, every ranked practice with the model's effect sentence, confidence,
 * field-observation count, the evidence-base line and the citations behind it,
 * the evidence mode with its reasons, the documented practices of a hybrid or
 * knowledge-led advisory (sources, never effect numbers), the honesty copy and
 * the share link — all from the same data as the screen.
 */
export function PrintSheet({
  data,
  advisory = null,
  params = null,
}: {
  /** The model payload — null for a knowledge-led advisory. */
  data: RecommendResponse | null;
  advisory?: AdviseResponse | null;
  /** The request, for the knowledge-led sheet that has no `data.query`. */
  params?: AdvisorParams | null;
}) {
  const t = useTranslations("advisor.results");
  const tp = useTranslations("advisor.results.print");
  const tcx = useTranslations("advisor.results.context");
  const tcard = useTranslations("advisor.results.card");
  const tdoc = useTranslations("advisor.results.documented");
  const tev = useTranslations("evidence");
  const tb = useTranslations("evidence.evidenceBase");
  const tsum = useTranslations("advisor.summary");
  const tc = useTranslations("common");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const reasonText = useReasonText();
  const explainCtx = useExplainOptional();
  const href = useClientValue(() => window.location.href, "");
  const generatedIso = useClientValue(() => new Date().toISOString().slice(0, 10), "");

  const mode = advisory?.mode ?? "model-led";
  const sourceMode = sourceModeOf(mode);
  const query = data?.query ?? {
    lat: params?.lat ?? 0,
    lon: params?.lon ?? 0,
    practice_family: params?.family ?? "",
    indicator: params?.indicator ?? "",
    crop_type: params?.crop ?? null,
    goal_direction: "",
  };
  const ctx = data?.details.context ?? advisory?.context ?? {};
  const belt = typeof ctx.aez_belt === "string" ? ctx.aez_belt : null;
  const explain = explainCtx?.state.status === "ready" ? explainCtx.state.result : null;
  const ragReady = !!explainCtx?.ragReady;
  const graphReady = !!explainCtx?.graphReady;
  const byPractice = new Map((data?.details.ranked ?? []).map((r) => [r.practice, r]));
  const citationsFor = (practice: string, tier: "evidence" | "guidance") => {
    if (!explain) return [];
    const all = explain.citations.filter((c) => (tier === "guidance") === (c.tier === "guidance"));
    const mine = all.filter((c) => c.practice === practice);
    return mine.length > 0 ? mine : all;
  };
  const candidates = advisory && mode !== "model-led" ? advisory.knowledge_candidates : [];

  return (
    <article className="print-only print-sheet" aria-hidden>
      <header className="print-sheet__header">
        <p className="print-sheet__brand">{tc("appName")} — {tc("tagline")}</p>
        <h1>{tp("title")}: {indicatorLabel(query.indicator, locale)}</h1>
        <p className="print-sheet__meta">
          {generatedIso ? tp("generatedOn", { date: format.dateTime(new Date(generatedIso), { dateStyle: "long" }) }) : null}
          {" · "}
          {sourceModeLabel(sourceMode, locale)}
        </p>
      </header>

      <section>
        <h2>{tp("request")}</h2>
        <dl className="print-sheet__dl">
          <dt>{tsum("location")}</dt>
          <dd className="tabular">
            {query.lat}, {query.lon}
            {belt ? ` · ${tcx("belt")}: ${aezName(belt, locale)}` : ""}
          </dd>
          <dt>{tsum("challenge")}</dt>
          <dd>{familyName(query.practice_family, locale)}</dd>
          <dt>{tsum("objective")}</dt>
          <dd>{indicatorLabel(query.indicator, locale)}</dd>
          <dt>{tsum("crop")}</dt>
          <dd>{query.crop_type ?? tsum("anyCrop")}</dd>
        </dl>
      </section>

      {Object.keys(ctx).length > 0 ? (
        <section>
          <h2>{tcx("title")}</h2>
          <table className="print-sheet__table">
            <tbody>
              {CONTEXT_FIELDS.filter((f) => ctx[f.key] != null && Number.isFinite(Number(ctx[f.key]))).map((f) => (
                <tr key={f.key}>
                  <th scope="row">{tcx(f.k)}</th>
                  <td className="tabular">
                    {format.number(Number(ctx[f.key]), { maximumFractionDigits: f.digits })}
                    {f.unit ? ` ${tcx(`units.${f.unit}`)}` : ""}
                  </td>
                  <td className="print-sheet__muted">{tcx(`meaning.${f.k}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {data ? (
        <section>
          <h2>{tp("practices")}</h2>
          <p className="print-sheet__muted">
            {t("rankedWithin", { family: familyName(data.query.practice_family, locale) })}
            {data.details.n_grounded != null
              ? ` · ${t("withEvidence", { grounded: data.details.n_grounded, candidates: data.details.n_candidates })}`
              : ""}
          </p>
          <ol className="print-sheet__practices">
            {data.recommendations.map((item, i) => {
              const ranked = byPractice.get(item.practice);
              const name = practiceName(item.practice, locale);
              const effect =
                locale === "en" || !ranked
                  ? item.effect
                  : effectSentence(ranked.pct_change, data.query.goal_direction, data.query.indicator, locale);
              const entry = explain?.evidence_base?.[item.practice];
              const studies = citationsFor(item.practice, "evidence");
              const guidance = citationsFor(item.practice, "guidance");
              return (
                <li key={item.practice}>
                  <h3>
                    {i + 1}. {name}
                    {name !== item.practice ? <span className="print-sheet__muted"> ({item.practice})</span> : null}
                  </h3>
                  <p>
                    <strong>{tp("effect")}:</strong> {effect}
                    {locale !== "en" ? <span className="print-sheet__muted"> — {item.effect}</span> : null}
                  </p>
                  <p>
                    <strong>{tcard("confidence")}:</strong> {confidenceLabel(data.details.confidence, locale)} — {confidenceMeaning(data.details.confidence, locale)}
                    {ranked ? ` · ${tcard("observations", { n: ranked.n_evidence })}` : ""}
                  </p>
                  {graphReady && entry ? (
                    <p>
                      <strong>{tp("evidenceBase")}:</strong>{" "}
                      {evidenceBaseSentence(item.practice, entry, tb, {
                        practice: (p) => practiceName(p, locale),
                        belt: (b) => aezName(b, locale),
                      })}
                    </p>
                  ) : null}
                  {studies.length > 0 || guidance.length > 0 ? (
                    <div>
                      <strong>{tp("sources")}:</strong>
                      <ul className="print-sheet__sources">
                        {[...studies, ...guidance].map((c, k) => (
                          <li key={`${c.ref ?? ""}${c.era_code ?? c.url ?? c.title ?? k}`}>
                            {c.ref ? `[${c.ref}] ` : ""}
                            {c.tier === "guidance" ? `[${tev("tier.guidance")}] ` : ""}
                            {[c.era_code, c.title ?? tev("untitledStudy"), c.year != null ? String(c.year) : null].filter(Boolean).join(" · ")}
                            {c.doi ? ` · doi:${c.doi}` : c.url ? ` · ${c.url}` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {ragReady && !explain ? <p className="print-sheet__muted">{tp("evidencePending")}</p> : null}
        </section>
      ) : null}

      {advisory && mode !== "model-led" ? (
        <section>
          <h2>{tdoc("title")}</h2>
          <p className="print-sheet__muted">{mode === "hybrid" ? tdoc("introHybrid") : tdoc("introKnowledge")}</p>
          {candidates.length === 0 ? <p>{tdoc("empty")}</p> : null}
          <ol className="print-sheet__practices">
            {candidates.map((c, i) => (
              <li key={c.key}>
                <h3>
                  {i + 1}. {candidateLabel(c, locale)}
                  {c.component && candidateLabel(c, locale) !== c.component ? <span className="print-sheet__muted"> ({c.component})</span> : null}
                </h3>
                <p>
                  <strong>{tdoc("why")}:</strong> {c.rationale_text}
                </p>
                <p className="print-sheet__muted">{c.sources.map((s) => tdoc(`source.${s}`)).join(" · ")}</p>
                {c.practices.length > 0 ? (
                  <p className="print-sheet__muted">
                    {tdoc("mapsTo")}: {c.practices.map((p) => practiceName(p, locale)).join(" · ")}
                  </p>
                ) : null}
                {c.citations.length > 0 ? (
                  <div>
                    <strong>{tp("sources")}:</strong>
                    <ul className="print-sheet__sources">
                      {c.citations.map((cit, k) => (
                        <li key={`${cit.ref ?? ""}${cit.era_code ?? cit.url ?? cit.title ?? k}`}>
                          {cit.ref ? `[${cit.ref}] ` : ""}
                          {cit.tier !== "evidence" ? `[${tierLabel(cit.tier, locale)}] ` : ""}
                          {citationLabel(cit, tev as never)}
                          {cit.doi ? ` · doi:${cit.doi}` : cit.url ? ` · ${cit.url}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
          <p className="print-sheet__muted">
            <em>{tdoc("disclaimer")}</em>
          </p>
        </section>
      ) : null}

      <section>
        <p>
          <strong>{t("source.label")}:</strong> {sourceModeLabel(sourceMode, locale)} — {sourceModeTooltip(sourceMode, locale)}
        </p>
        {advisory && advisory.reasons.length > 0 ? (
          <ul className="print-sheet__sources">
            {advisory.reasons.map((r, i) => (
              <li key={`${r.key}-${i}`}>{reasonText(r)}</li>
            ))}
          </ul>
        ) : null}
        {data ? (
          <p className="print-sheet__muted" lang="en">
            {data.details.note}
          </p>
        ) : null}
        <p>
          <em>{t("disclaimer")}</em>
        </p>
      </section>

      <footer className="print-sheet__footer">
        <p>{tp("footer")}</p>
        {href ? (
          <p>
            {tp("shareLink")}: <span className="print-sheet__link">{href}</span>
          </p>
        ) : null}
      </footer>
    </article>
  );
}
