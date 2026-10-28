"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { aezName } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import type { RecommendResponse } from "@/lib/types";
import { Card } from "@/components/ui/card";

const FIELDS: { key: string; k: string; unit: "mm" | "m" | "percent" | "days" | "celsius" | null; digits: number }[] = [
  { key: "Rainfall", k: "rainfall", unit: "mm", digits: 0 },
  { key: "temp_mean_annual", k: "temp", unit: "celsius", digits: 1 },
  { key: "Altitude_r", k: "altitude", unit: "m", digits: 0 },
  { key: "slope", k: "slope", unit: "percent", digits: 1 },
  { key: "soil_clay", k: "clay", unit: "percent", digits: 0 },
  { key: "soil_ph", k: "ph", unit: null, digits: 1 },
  { key: "soil_soc", k: "soc", unit: null, digits: 1 },
  { key: "lgp_days", k: "lgp", unit: "days", digits: 0 },
];

/** The context the model scored against — each value with its unit and meaning.
 *  `compact` is the chat's inline variant (U2): same fields, tighter grid. */
export function ContextCard({ data, compact = false, title }: { data: RecommendResponse; compact?: boolean; title?: string }) {
  const t = useTranslations("advisor.results.context");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const ctx = data.details.context ?? {};
  const belt = typeof ctx.aez_belt === "string" ? ctx.aez_belt : null;
  const rows = FIELDS.filter((f) => ctx[f.key] != null && Number.isFinite(Number(ctx[f.key])));

  return (
    <Card className={compact ? "p-3 sm:p-4" : "p-4 sm:p-5"}>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{title ?? t("title")}</p>
      {belt ? (
        <div className={compact ? "mt-2" : "mt-3"}>
          <p className="text-sm text-muted">{t("belt")}</p>
          <p className={compact ? "text-base font-semibold text-text" : "text-lg font-semibold text-text"}>{aezName(belt, locale)}</p>
          {compact ? null : <p className="text-xs text-muted">{t("meaning.belt")}</p>}
        </div>
      ) : null}
      <dl className={compact ? "mt-3 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4" : "mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4"}>
        {rows.map((f) => (
          <div key={f.key}>
            <dt className="text-xs text-muted">{t(f.k)}</dt>
            <dd className="tabular text-base font-semibold text-text">
              {format.number(Number(ctx[f.key]), { maximumFractionDigits: f.digits })}
              {f.unit ? <span className="ml-1 text-sm font-normal text-muted">{t(`units.${f.unit}`)}</span> : null}
            </dd>
            {compact ? null : <dd className="text-xs text-muted">{t(`meaning.${f.k}`)}</dd>}
          </div>
        ))}
      </dl>
    </Card>
  );
}
