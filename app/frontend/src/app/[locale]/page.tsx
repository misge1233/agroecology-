import { setRequestLocale } from "next-intl/server";
import { HomeHero } from "@/components/home/hero";
import { HomeHow } from "@/components/home/how";
import { TrustStrip } from "@/components/home/trust-strip";
import { HomeFamilies } from "@/components/home/families";

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <>
      <HomeHero />
      <TrustStrip />
      <HomeHow />
      <HomeFamilies />
    </>
  );
}
