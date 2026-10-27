"use client";

import { ArrowRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { familyBlurb, familyShort } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { useMetadata } from "@/components/metadata-provider";
import { Card, CardContent } from "@/components/ui/card";
import { FAMILY_ICONS } from "@/components/advisor/family-icons";

export function HomeFamilies() {
  const t = useTranslations("home.families");
  const locale = useLocale() as Locale;
  const { meta } = useMetadata();
  const families = meta?.practice_families ?? Object.keys(FAMILY_ICONS);
  return (
    <section className="mx-auto max-w-content px-4 py-10 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("eyebrow")}</p>
      <h2 className="mt-2 text-2xl">{t("title")}</h2>
      <p className="mt-2 max-w-2xl text-muted">{t("subtitle")}</p>
      <ul className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {families.map((family) => {
          const Icon = FAMILY_ICONS[family] ?? FAMILY_ICONS["Crop production and management"];
          const short = familyShort(family, locale);
          return (
            <li key={family}>
              <Link href={{ pathname: "/advisor", query: { family } }} className="block h-full rounded-card">
                <Card className="h-full transition-colors duration-base hover:border-primary/50">
                  <CardContent className="p-5 sm:p-5">
                    <Icon className="h-5 w-5 text-primary" aria-hidden />
                    <h3 className="mt-3 text-lg">{short}</h3>
                    <p className="mt-2 text-sm text-muted">{familyBlurb(family, locale)}</p>
                    <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary">
                      {t("open", { family: short })}
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </span>
                  </CardContent>
                </Card>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
