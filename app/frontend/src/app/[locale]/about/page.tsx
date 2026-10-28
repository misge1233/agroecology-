import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "about" });
  return { title: t("title") };
}

export default async function AboutPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "about" });
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl sm:text-3xl">{t("title")}</h1>
      <p className="mt-3 text-lg text-muted">{t("lead")}</p>

      <section className="mt-8 space-y-6">
        <Card>
          <CardHeader><CardTitle as="h2">{t("what.title")}</CardTitle></CardHeader>
          <CardContent><p className="text-sm leading-relaxed text-muted">{t("what.body")}</p></CardContent>
        </Card>

        <Card id="confidence">
          <CardHeader><CardTitle as="h2">{t("confidence.title")}</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-muted">{t("confidence.body")}</p>
            <ul className="space-y-2">
              <li className="flex items-start gap-2"><Badge variant="primary">●</Badge><span>{t("confidence.high")}</span></li>
              <li className="flex items-start gap-2"><Badge variant="warning">●</Badge><span>{t("confidence.medium")}</span></li>
              <li className="flex items-start gap-2"><Badge variant="neutral">●</Badge><span>{t("confidence.low")}</span></li>
            </ul>
          </CardContent>
        </Card>

        <Card id="sources">
          <CardHeader><CardTitle as="h2">{t("sources.title")}</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 pl-5 text-sm text-muted">
              <li>{t("sources.evidence")}</li>
              <li>{t("sources.geo")}</li>
              <li>{t("sources.guidance")}</li>
              <li>{t("sources.practice")}</li>
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle as="h2">{t("authors.title")}</CardTitle></CardHeader>
          <CardContent><p className="text-sm text-muted">{t("authors.body")}</p></CardContent>
        </Card>

        <Card id="licence">
          <CardHeader><CardTitle as="h2">{t("licence.title")}</CardTitle></CardHeader>
          <CardContent><p className="text-sm text-muted">{t("licence.body")}</p></CardContent>
        </Card>
      </section>

      <Button className="mt-8" size="lg" asChild>
        <Link href="/advisor">{t("cta")}</Link>
      </Button>
    </div>
  );
}
