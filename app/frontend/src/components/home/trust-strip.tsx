"use client";

import { useLocale, useTranslations } from "next-intl";
import { useMetadata } from "@/components/metadata-provider";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Live figures from /metadata — nothing hard-coded. Evidence counts come from
 * the additive `evidence` block (U1). U3: one card overlapping the hero, the
 * four evidence-base figures only (family/objective counts repeat the page).
 */
export function TrustStrip() {
  const t = useTranslations("home.trust");
  const locale = useLocale();
  const { meta, loading } = useMetadata();
  const fmt = (n: number) => new Intl.NumberFormat(locale).format(n);

  const figures = meta
    ? [
        { key: "observations", value: meta.evidence?.n_observations },
        { key: "studies", value: meta.evidence?.n_studies },
        { key: "practices", value: meta.evidence?.n_practices },
        { key: "belts", value: meta.evidence?.n_belts },
      ].filter((f) => typeof f.value === "number")
    : [];

  return (
    <section aria-labelledby="evidence-base" className="relative z-10 -mt-16">
      <div className="container-page">
        <div className="rounded-panel border border-border bg-surface px-6 py-7 shadow-2 sm:px-10">
          <h2 id="evidence-base" className="sr-only">
            {t("eyebrow")}
          </h2>
          {loading ? (
            <div className="grid grid-cols-2 gap-6 md:grid-cols-4" aria-busy>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="mx-auto h-14 w-28" />
              ))}
              <span className="sr-only">{t("loading")}</span>
            </div>
          ) : figures.length === 0 ? (
            <p className="text-center text-sm text-muted">{t("unavailable")}</p>
          ) : (
            <dl className="grid grid-cols-2 gap-y-6 md:grid-cols-4 md:divide-x md:divide-border">
              {figures.map((f) => (
                <div key={f.key} className="flex flex-col items-center text-center md:px-4">
                  <dd className="text-3xl font-semibold tabular text-primary sm:text-4xl">{fmt(f.value as number)}</dd>
                  <dt className="mt-1.5 text-sm text-muted">{t(f.key)}</dt>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </section>
  );
}
