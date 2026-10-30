"use client";

import Image from "next/image";
import { ArrowRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { familyBlurb, familyShort } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { useMetadata } from "@/components/metadata-provider";
import { FAMILY_ICONS, FAMILY_IMAGES } from "@/components/advisor/family-icons";

export function HomeFamilies() {
  const t = useTranslations("home.families");
  const locale = useLocale() as Locale;
  const { meta } = useMetadata();
  const families = meta?.practice_families ?? Object.keys(FAMILY_ICONS);
  return (
    <section aria-labelledby="families-title" className="py-20 sm:py-24">
      <div className="container-page">
        <div className="max-w-2xl">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h2 id="families-title" className="mt-3 text-balance text-3xl">
            {t("title")}
          </h2>
          <p className="mt-4 text-lg text-muted">{t("subtitle")}</p>
        </div>
        <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
          {families.map((family) => {
            const Icon = FAMILY_ICONS[family] ?? FAMILY_ICONS["Crop production and management"];
            const image = FAMILY_IMAGES[family];
            return (
              <li key={family}>
                <Link
                  href={{ pathname: "/advisor", query: { family } }}
                  className="group flex h-full overflow-hidden rounded-card border border-border bg-surface shadow-1 transition duration-base hover:-translate-y-0.5 hover:shadow-2 sm:flex-col"
                >
                  {/* Phones: a compact row (thumbnail left); sm+: photo on top. */}
                  <div className="relative w-28 shrink-0 overflow-hidden bg-surface-2 sm:aspect-[4/3] sm:w-auto">
                    {image ? (
                      <Image
                        src={image}
                        alt=""
                        fill
                        sizes="(min-width: 1024px) 20vw, (min-width: 640px) 50vw, 112px"
                        className="object-cover transition-transform duration-base group-hover:scale-[1.03]"
                      />
                    ) : null}
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col p-4 sm:p-5">
                    <div className="flex items-center gap-2 text-primary">
                      <Icon className="h-4 w-4 shrink-0" aria-hidden />
                      <h3 className="text-base font-semibold text-text">{familyShort(family, locale)}</h3>
                    </div>
                    <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{familyBlurb(family, locale)}</p>
                    <ArrowRight
                      className="mt-3 hidden h-4 w-4 text-primary sm:block transition-transform duration-base group-hover:translate-x-1"
                      aria-hidden
                    />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
