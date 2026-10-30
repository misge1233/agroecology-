import {
  BookOpenText,
  BrainCircuit,
  ChevronRight,
  Globe2,
  Layers,
  Library,
  Network,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

/** The four system layers, in pipeline order (see docs/decisions/rag_design.md). */
const LAYERS: { key: "geo" | "model" | "rag" | "graph"; icon: LucideIcon }[] = [
  { key: "geo", icon: Layers },
  { key: "model", icon: BrainCircuit },
  { key: "rag", icon: BookOpenText },
  { key: "graph", icon: Network },
];

const ROADMAP: { key: "wocat" | "global"; icon: LucideIcon }[] = [
  { key: "wocat", icon: Library },
  { key: "global", icon: Globe2 },
];

/**
 * "Under the hood" (U4): how the geospatial stack, the ML ranker, RAG and the
 * knowledge graph fit together, the numbers guarantee (CLAUDE.md doctrine 1)
 * and the roadmap. Copy only — no figures, so nothing here can drift from the model.
 */
export function HomeArchitecture() {
  const t = useTranslations("home.architecture");
  return (
    <section aria-labelledby="arch-title" className="border-y border-border bg-surface-2 py-20 sm:py-24">
      <div className="container-page">
        <div className="max-w-3xl">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h2 id="arch-title" className="mt-3 text-balance text-3xl">
            {t("title")}
          </h2>
          <p className="mt-4 text-lg text-muted">{t("subtitle")}</p>
        </div>

        <ol className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {LAYERS.map(({ key, icon: Icon }, i) => (
            <li key={key} className="relative flex flex-col rounded-card border border-border bg-surface p-6 shadow-1">
              <div className="flex items-center justify-between">
                <span className="flex h-11 w-11 items-center justify-center rounded-control bg-primary-soft text-primary">
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted">
                  {t("layer", { n: i + 1 })}
                </span>
              </div>
              <h3 className="mt-5 text-lg">{t(`layers.${key}.title`)}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{t(`layers.${key}.body`)}</p>
              <p className="mt-5 border-t border-border pt-4 text-xs leading-relaxed text-muted">{t(`layers.${key}.tag`)}</p>
              {/* Pipeline connector to the next layer (single-row layout only). */}
              {i < LAYERS.length - 1 ? (
                <span
                  aria-hidden
                  className="absolute -right-6 top-1/2 z-10 hidden h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-surface text-primary shadow-1 xl:flex"
                >
                  <ChevronRight className="h-4 w-4" />
                </span>
              ) : null}
            </li>
          ))}
        </ol>

        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <div className="flex gap-4 rounded-card border border-primary/25 bg-primary-soft p-6">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-control bg-primary text-primary-fg">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <h3 className="text-lg">{t("guardrail.title")}</h3>
              <p className="mt-2 text-sm leading-relaxed text-text">{t("guardrail.body")}</p>
            </div>
          </div>

          <div className="rounded-card border border-dashed border-border bg-surface p-6">
            <h3 className="text-lg">{t("roadmap.title")}</h3>
            <ul className="mt-4 space-y-4">
              {ROADMAP.map(({ key, icon: Icon }) => (
                <li key={key} className="flex gap-3">
                  <Icon className="mt-0.5 h-5 w-5 shrink-0 text-secondary-text" aria-hidden />
                  <div>
                    <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                      {t(`roadmap.${key}.title`)}
                      <span className="rounded-full bg-secondary-soft px-2 py-0.5 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-secondary-text">
                        {t("roadmap.badge")}
                      </span>
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-muted">{t(`roadmap.${key}.body`)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
