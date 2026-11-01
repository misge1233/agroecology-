"use client";

import { useLocale, useTranslations } from "next-intl";
import { confidenceLabel, indicatorNoun } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { displayText } from "@/lib/numbers";
import type { PracticeEvidence, StudyEvidence } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useCitations } from "@/components/citations";

/** % change for a log response ratio (the same conversion the backend uses). */
const pct = (log: number) => (Math.exp(log) - 1) * 100;

/** The studies shown for a practice: the leading ones, else the closest few. */
export function shownStudies(b: PracticeEvidence, max = 3): StudyEvidence[] {
  const lead = new Set(b.study?.refs ?? []);
  const leading = b.studies.filter((s) => lead.has(s.ref));
  return (leading.length ? leading : b.studies).slice(0, max);
}

/**
 * "Why this?" for one practice (U9, D1): the labelled values behind the
 * headline — the model estimate for this area and the effects reported by
 * field studies — which one leads, and one line when they disagree. Every
 * number is a value of the evidence bundle (model output or a study effect
 * computed from dataset rows); display rounding is the shared rule.
 */
export function EvidenceWhy({ bundle, indicator }: { bundle: PracticeEvidence; indicator: string }) {
  const t = useTranslations("advisor.results.card");
  const tf = useTranslations("advisor.results.card.fusion");
  const te = useTranslations("evidence.evidenceBase");
  const locale = useLocale() as Locale;
  const { label } = useCitations();
  const noun = indicatorNoun(indicator, locale);
  const m = bundle.model;
  const studies = shownStudies(bundle);
  const modelLeads = bundle.lead_source === "model";
  const dir = (v: number) => (v < 0 ? "less" : "more");

  return (
    <div className="space-y-3">
      <ul className="space-y-2 text-sm">
        <li className="flex items-start gap-2">
          <LeadTag leads={modelLeads} />
          <span>
            {tf("labelModel", {
              value: displayText(Math.abs(m.value)),
              dir: dir(m.value),
              indicator: noun,
              confidence: confidenceLabel(m.confidence, locale),
              studies: te("studies", { n: m.n_studies }),
              observations: t("observations", { n: m.n_obs }),
            })}
          </span>
        </li>
        {studies.map((s) => {
          const ref = label({ tier: "evidence", era_code: s.era_code, study_no: s.study_no, title: s.title }) ?? s.study_no;
          const about = s.title ? ` (${[s.title, s.year].filter(Boolean).join(", ")})` : "";
          return (
            <li key={s.ref} className="flex items-start gap-2">
              <LeadTag leads={!modelLeads && (bundle.study?.refs ?? []).includes(s.ref)} />
              <span>
                {tf("labelStudy", {
                  ref,
                  about,
                  value: displayText(Math.abs(s.effect.value)),
                  dir: dir(s.effect.value),
                  indicator: noun,
                  observations: t("observations", { n: s.n_obs }),
                })}
              </span>
            </li>
          );
        })}
      </ul>
      {bundle.disagreement ? (
        <p className="rounded-control border border-warning/50 bg-warning-soft px-3 py-2 text-sm text-text">{tf("disagree")}</p>
      ) : null}
      <EffectDots bundle={bundle} studies={studies} />
    </div>
  );
}

function LeadTag({ leads }: { leads: boolean }) {
  const tf = useTranslations("advisor.results.card.fusion");
  return (
    <span
      className={cn(
        "mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold uppercase tracking-[0.04em]",
        leads ? "bg-primary text-primary-fg" : "bg-surface-2 text-muted ring-1 ring-border"
      )}
    >
      {leads ? tf("leads") : tf("supports")}
    </span>
  );
}

/**
 * Model estimate and each shown study as a dot with its ±1 SE interval, on an
 * axis that always includes 0 (the old single bar ran from −82% to −78%).
 * Hidden when there is only one value to show.
 */
function EffectDots({ bundle, studies }: { bundle: PracticeEvidence; studies: StudyEvidence[] }) {
  const tf = useTranslations("advisor.results.card.fusion");
  const { label } = useCitations();
  const m = bundle.model;
  const modelLog = Math.log(1 + m.value / 100);
  const rows = [
    { key: "model", name: tf("sourceModel"), lo: pct(modelLog - m.se_log), mid: m.value, hi: pct(modelLog + m.se_log), model: true },
    ...studies.map((s) => ({
      key: s.ref,
      name: `[${label({ tier: "evidence", era_code: s.era_code, study_no: s.study_no, title: s.title }) ?? s.study_no}]`,
      lo: pct(s.mean_log_rr - s.se_log),
      mid: s.effect.value,
      hi: pct(s.mean_log_rr + s.se_log),
      model: false,
    })),
  ];
  if (rows.length < 2) return null;
  const min = Math.min(0, ...rows.map((r) => r.lo));
  const max = Math.max(0, ...rows.map((r) => r.hi));
  const span = max - min || 1;
  const x = (v: number) => 4 + ((v - min) / span) * 92; // % of the plot width, 4% padding
  const zero = x(0);
  return (
    <figure className="pt-1">
      <figcaption className="sr-only">{tf("studyChart")}</figcaption>
      <div className="space-y-1.5" aria-hidden>
        {rows.map((r) => (
          <div key={r.key} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem] items-center gap-2 text-xs">
            <span className="truncate text-muted">{r.name}</span>
            <span className="relative h-5">
              <span className="absolute inset-y-0 w-px bg-border" style={{ left: `${zero}%` }} />
              <span
                className={cn("absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full", r.model ? "bg-primary/40" : "bg-accent/40")}
                style={{ left: `${x(r.lo)}%`, width: `${Math.max(0.5, x(r.hi) - x(r.lo))}%` }}
              />
              <span
                className={cn(
                  "absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface",
                  r.model ? "bg-primary" : "bg-accent"
                )}
                style={{ left: `${x(r.mid)}%` }}
              />
            </span>
            <span className="text-right tabular text-text">{displayText(r.mid)}%</span>
          </div>
        ))}
        <div className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem] gap-2 text-[0.625rem] text-muted">
          <span />
          <span className="relative h-3">
            <span className="absolute -translate-x-1/2 tabular" style={{ left: `${zero}%` }}>0</span>
          </span>
          <span />
        </div>
      </div>
    </figure>
  );
}
