import type { Metadata } from "next";
import { ArrowRight, BookOpen, Database, Globe2, Library } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shell/page-header";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "about" });
  return { title: t("title") };
}

const SOURCES = [
  { key: "evidence", icon: Database },
  { key: "geo", icon: Globe2 },
  { key: "guidance", icon: BookOpen },
  { key: "practice", icon: Library },
] as const;

const CONFIDENCE = [
  { key: "high", dot: "bg-primary" },
  { key: "medium", dot: "bg-warning" },
  { key: "low", dot: "bg-muted" },
] as const;

export default async function AboutPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "about" });
  return (
    <>
      <PageHeader title={t("title")} description={t("lead")} />

      <div className="container-page grid gap-12 py-14 sm:py-16 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-16">
        <div className="min-w-0 space-y-14">
          <section aria-labelledby="what">
            <h2 id="what" className="text-2xl">{t("what.title")}</h2>
            <p className="mt-4 max-w-3xl leading-relaxed text-muted">{t("what.body")}</p>
          </section>

          <section id="confidence" aria-labelledby="confidence-title" className="scroll-mt-24">
            <h2 id="confidence-title" className="text-2xl">{t("confidence.title")}</h2>
            <p className="mt-4 max-w-3xl leading-relaxed text-muted">{t("confidence.body")}</p>
            <ul className="mt-6 divide-y divide-border rounded-card border border-border bg-surface">
              {CONFIDENCE.map(({ key, dot }) => (
                <li key={key} className="flex items-start gap-3 px-5 py-4 text-sm">
                  <span aria-hidden className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${dot}`} />
                  <span className="leading-relaxed">{t(`confidence.${key}`)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section id="sources" aria-labelledby="sources-title" className="scroll-mt-24">
            <h2 id="sources-title" className="text-2xl">{t("sources.title")}</h2>
            <ul className="mt-6 grid gap-4 sm:grid-cols-2">
              {SOURCES.map(({ key, icon: Icon }) => (
                <li key={key} className="rounded-card border border-border bg-surface p-5">
                  <span className="flex h-10 w-10 items-center justify-center rounded-control bg-primary-soft text-primary">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <p className="mt-4 text-sm leading-relaxed text-muted">{t(`sources.${key}`)}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-[calc(var(--header-h)+2rem)] lg:self-start">
          <div className="rounded-card border border-border bg-surface-2 p-6">
            <h2 className="text-base font-semibold">{t("authors.title")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{t("authors.body")}</p>
            <h2 id="licence" className="mt-6 scroll-mt-24 border-t border-border pt-6 text-base font-semibold">
              {t("licence.title")}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{t("licence.body")}</p>
          </div>
          <Button size="lg" className="w-full" asChild>
            <Link href="/advisor">
              {t("cta")}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
        </aside>
      </div>
    </>
  );
}
