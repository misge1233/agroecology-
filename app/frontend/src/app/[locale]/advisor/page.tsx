import type { Metadata } from "next";
import { Suspense } from "react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AdvisorFlow, AdvisorSkeleton } from "@/components/advisor/advisor-flow";

// Rendered per request: the request lives in the query string, so the first
// step (or the results skeleton) is server-rendered with the real params
// instead of a static shell that bails out to client rendering.
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "advisor" });
  return { title: t("title"), description: t("subtitle") };
}

export default async function AdvisorPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    // useSearchParams needs a Suspense boundary for static rendering.
    <Suspense fallback={<AdvisorSkeleton />}>
      <AdvisorFlow />
    </Suspense>
  );
}
