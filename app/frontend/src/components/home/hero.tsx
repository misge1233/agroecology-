import Image from "next/image";
import { ArrowRight, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";
/**
 * Hero photo (owner-provided, 1 Nov 2026): an Ethiopian highland landscape at
 * dawn: stone-bunded terraces with grass strips, a water-harvesting pond,
 * maize and cereal fields, and a farming family with oxen. Static import, so
 * Next knows its size (no layout shift) and paints a blurred preview at once.
 * Source: public/practices/hero_image.png, optimised to WebP (1915×821).
 */
import heroImage from "../../../public/hero/agroecology-landscape.webp";

export function HomeHero() {
  const t = useTranslations("home.hero");
  const tc = useTranslations("common");
  return (
    <section className="relative isolate overflow-hidden bg-forest-950">
      {/* Decorative: the headline carries the meaning. */}
      <Image
        src={heroImage}
        alt=""
        fill
        priority
        placeholder="blur"
        sizes="100vw"
        quality={80}
        // Phones keep the family and the terraces (right of the frame) in view;
        // wide screens show the whole valley behind the headline.
        className="-z-20 object-cover object-[78%_center] md:object-[65%_center] xl:object-center"
      />
      {/* Scrim: dense behind the text column (the bright dawn sky sits there), clear
          on the right so the terraces and the farmers read. Darker on phones, where
          the text covers the whole frame. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-gradient-to-r from-forest-950/90 via-forest-950/75 to-forest-950/45 md:via-forest-950/60 md:to-forest-950/5"
      />
      <div aria-hidden className="absolute inset-x-0 bottom-0 -z-10 h-32 bg-gradient-to-t from-forest-950/60 to-transparent" />

      <div className="container-page flex min-h-[32rem] flex-col justify-center pb-28 pt-16 sm:min-h-[36rem] lg:min-h-[40rem]">
        <div className="max-w-2xl">
          <h1 className="text-balance text-white">
            {/* Brand in the forest green, tagline lighter: two lines, two roles. */}
            {/* The rule spans the full brand: harvest gold fading into the brand green. */}
            <span className="inline-block">
              <span className="block text-4xl font-semibold text-forest-200 sm:text-5xl">{tc("appName")}</span>
              <span aria-hidden className="mt-2.5 block h-1 w-full rounded-full bg-gradient-to-r from-[#E0A43A] to-forest-200" />
            </span>
            <span className="mt-5 block text-3xl font-normal text-white/95 sm:text-4xl">{t("title")}</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-white/85">{t("subtitle")}</p>
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
