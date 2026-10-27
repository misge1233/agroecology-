import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ChatPanel } from "@/components/chat-panel";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "nav" });
  return { title: t("chat") };
}

export default async function ChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  // `?q=` pre-fills the composer (Advisor → "Explain in chat"); nothing auto-sends.
  const { q } = await searchParams;
  const seed = typeof q === "string" ? q.slice(0, 4000) : null;
  return <ChatPanel seedMessage={seed} />;
}
