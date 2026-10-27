"use client";

import { useLocale, useTranslations } from "next-intl";
import { useMetadata } from "@/components/metadata-provider";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Live figures from /metadata — nothing hard-coded. Evidence counts come from
 * the additive `evidence` block (U1); families/objectives from the lists.
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
        { key: "families", value: meta.practice_families.length },
        { key: "objectives", value: meta.indicators.length },
      ].filter((f) => typeof f.value === "number")
    : [];

  return (
    <section className="border-y border-border bg-surface">
      <div className="mx-auto max-w-content px-4 py-8 sm:px-6">
        <p className="text-center text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("eyebrow")}</p>
        {loading ? (
          <div className="mt-6 grid grid-cols-2 gap-6 md:grid-cols-3 lg:grid-cols-6" aria-busy>
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="mx-auto h-12 w-24" />
            ))}
            <span className="sr-only">{t("loading")}</span>
          </div>
        ) : figures.length === 0 ? (
          <p className="mt-4 text-center text-sm text-muted">{t("unavailable")}</p>
        ) : (
          <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-6 md:grid-cols-3 lg:grid-cols-6">
            {figures.map((f) => (
              <div key={f.key} className="text-center">
                <dd className="text-2xl font-semibold tabular text-text sm:text-3xl">{fmt(f.value as number)}</dd>
                <dt className="mt-1 text-sm text-muted">{t(f.key)}</dt>
              </div>
            ))}
          </dl>
        )}
      </div>
    </section>
  );
}
