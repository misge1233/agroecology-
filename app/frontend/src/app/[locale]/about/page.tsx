import type { Metadata } from "next";
import Image from "next/image";
import { ArrowRight, BookOpen, Database, Globe2, Library, Mail } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { confidenceLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ContourLines } from "@/components/shell/contour-lines";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "about" });
  return { title: t("title") };
}

/** Public contact address for the AgroAdvisor-ET team (owner-provided, U8). */
const CONTACT_EMAIL = "m.tuse@cgiar.org";

const SOURCES = [
  { key: "evidence", icon: Database },
  { key: "geo", icon: Globe2 },
  { key: "guidance", icon: BookOpen },
  { key: "practice", icon: Library },
] as const;

/** Confidence levels: colour bar, dot and soft background per level (tokens only). */
const CONFIDENCE = [
  // Outlined pills on the white card: amber text on the amber-soft fill is only 4.26:1.
  { key: "high", bar: "bg-primary", soft: "border border-primary text-primary" },
  { key: "medium", bar: "bg-warning", soft: "border border-warning text-warning-text" },
  { key: "low", bar: "bg-muted", soft: "border border-border text-muted" },
] as const;

/**
 * About (U8): tinted hero, then alternating white / surface-2 sections:
 * what it is (with a field photo), how to read confidence (three levels side
 * by side), data sources (card grid), and a full-width contact band.
 */
export default async function AboutPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "about" });
  const tr = await getTranslations({ locale, namespace: "home.architecture.roadmap" });

  return (
    <>
      {/* Hero */}
      <section className="relative isolate overflow-hidden border-b border-border bg-primary-soft">
        <ContourLines />
        <div className="container-page py-14 sm:py-20">
          <h1 className="max-w-3xl text-balance text-4xl sm:text-5xl">{t("title")}</h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted">{t("lead")}</p>
          <Button size="lg" className="mt-8" asChild>
            <Link href="/advisor">
              {t("cta")}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
        </div>
      </section>

      {/* What it is */}
      <section aria-labelledby="what" className="py-16 sm:py-20">
        <div className="container-page grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <div>
            <h2 id="what" className="text-3xl">
              {t("what.title")}
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted">{t("what.body")}</p>
          </div>
          <div className="relative aspect-[4/3] overflow-hidden rounded-panel border border-border shadow-2">
            <Image
              src="/practices/multistrata-agroforestry.webp"
              alt=""
              fill
              sizes="(min-width: 1024px) 40vw, 100vw"
              className="object-cover"
            />
          </div>
        </div>
      </section>

      {/* How to read confidence */}
      <section id="confidence" aria-labelledby="confidence-title" className="scroll-mt-20 border-y border-border bg-surface-2 py-16 sm:py-20">
        <div className="container-page">
          <div className="max-w-3xl">
            <h2 id="confidence-title" className="text-3xl">
              {t("confidence.title")}
            </h2>
            <p className="mt-4 text-lg leading-relaxed text-muted">{t("confidence.body")}</p>
          </div>
          <ul className="mt-10 grid gap-5 md:grid-cols-3">
            {CONFIDENCE.map(({ key, bar, soft }) => (
              <li key={key} className="overflow-hidden rounded-card border border-border bg-surface shadow-1">
                <span aria-hidden className={cn("block h-1.5", bar)} />
                <div className="p-6">
                  <span className={cn("inline-flex rounded-full px-3 py-1 text-xs font-semibold", soft)}>
                    {confidenceLabel(key, locale as Locale)}
                  </span>
                  <p className="mt-4 leading-relaxed text-text first-letter:uppercase">{t(`confidence.${key}`)}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Data sources */}
      <section id="sources" aria-labelledby="sources-title" className="scroll-mt-20 py-16 sm:py-20">
        <div className="container-page">
          <h2 id="sources-title" className="text-3xl">
            {t("sources.title")}
          </h2>
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {SOURCES.map(({ key, icon: Icon }) => (
              <li key={key} className="flex flex-col rounded-card border border-border bg-surface p-6 shadow-1">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex h-11 w-11 items-center justify-center rounded-control bg-primary-soft text-primary">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  {key === "practice" ? (
                    <span className="rounded-full bg-secondary-soft px-2 py-0.5 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-secondary-text">
                      {tr("badge")}
                    </span>
                  ) : null}
                </div>
                <h3 className="mt-5 text-base font-semibold">{t(`sources.names.${key}`)}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{t(`sources.${key}`)}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Contact: one horizontal band */}
      <section id="contact" aria-labelledby="contact-title" className="scroll-mt-20 border-t border-border bg-surface-2 py-16 sm:py-20">
        <div className="container-page">
          <div className="flex flex-col gap-8 rounded-panel border border-border bg-surface p-8 shadow-1 sm:p-10 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-5">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary text-primary-fg shadow-1">
                <Mail className="h-6 w-6" aria-hidden />
              </span>
              <div className="max-w-xl">
                <h2 id="contact-title" className="text-2xl">
                  {t("contact.title")}
                </h2>
                <p className="mt-2 leading-relaxed text-muted">{t("contact.body")}</p>
              </div>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center lg:shrink-0">
              <span className="select-all rounded-control border border-border bg-surface-2 px-4 py-2.5 text-base font-medium text-text tabular">
                {CONTACT_EMAIL}
              </span>
              <Button size="lg" asChild>
                <a href={`mailto:${CONTACT_EMAIL}`}>
                  <Mail className="h-4 w-4" aria-hidden />
                  {t("contact.cta")}
                </a>
              </Button>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
