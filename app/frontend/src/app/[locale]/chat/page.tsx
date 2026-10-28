import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { CHAT_NAMESPACES, pickMessages } from "@/i18n/messages";
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
  const messages = pickMessages(await getMessages(), CHAT_NAMESPACES);
  return (
    <NextIntlClientProvider messages={messages}>
      <ChatPanel seedMessage={seed} />
    </NextIntlClientProvider>
  );
}
