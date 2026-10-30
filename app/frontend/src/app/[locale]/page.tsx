import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { HOME_NAMESPACES, pickMessages } from "@/i18n/messages";
import { HomeHero } from "@/components/home/hero";
import { HomeHow } from "@/components/home/how";
import { TrustStrip } from "@/components/home/trust-strip";
import { HomeFamilies } from "@/components/home/families";
import { HomeCta } from "@/components/home/cta-band";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const messages = pickMessages(await getMessages(), HOME_NAMESPACES);
  return (
    <NextIntlClientProvider messages={messages}>
      <HomeHero />
      <TrustStrip />
      <HomeHow />
      <HomeFamilies />
      <HomeCta />
    </NextIntlClientProvider>
  );
}
