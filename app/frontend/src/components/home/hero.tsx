import Image from "next/image";
import { ArrowRight, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

/** Hero photo: terraced, grass-strip-stabilised highland fields (agronomic + biological SWC). */
const HERO_IMAGE = "/practices/agronomic-biological-swcp.webp";

export function HomeHero() {
  const t = useTranslations("home.hero");
  return (
    <section className="relative isolate overflow-hidden bg-forest-950">
      {/* Decorative: the headline carries the meaning. */}
      <Image
        src={HERO_IMAGE}
        alt=""
        fill
        priority
        sizes="100vw"
        className="-z-20 object-cover object-[center_40%]"
      />
      {/* Scrim: solid behind the text column, clear on the right so the landscape reads. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-gradient-to-r from-forest-950/95 via-forest-950/75 to-forest-950/25"
      />
      <div aria-hidden className="absolute inset-x-0 bottom-0 -z-10 h-32 bg-gradient-to-t from-forest-950/60 to-transparent" />

      <div className="container-page flex min-h-[32rem] flex-col justify-center pb-28 pt-16 sm:min-h-[36rem] lg:min-h-[40rem]">
        <div className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.1em] text-forest-200">{t("eyebrow")}</p>
          <h1 className="mt-4 text-balance text-4xl font-semibold text-white sm:text-5xl">{t("title")}</h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-white/85">{t("subtitle")}</p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Button size="xl" variant="inverse" asChild>
              <Link href="/advisor">
                {t("ctaAdvisor")}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </Button>
            <Button size="xl" variant="outline-inverse" asChild>
              <Link href="/chat">
                <MessageSquare className="h-4 w-4" aria-hidden />
                {t("ctaChat")}
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
