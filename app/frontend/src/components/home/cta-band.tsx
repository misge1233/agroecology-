import { ArrowRight, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

/** Closing call to action: the two ways in (guided Advisor, free-text chat). */
export function HomeCta() {
  const t = useTranslations("home");
  return (
    <section aria-labelledby="cta-title" className="py-20 sm:py-24">
      <div className="container-page">
        <div className="relative overflow-hidden rounded-panel bg-forest-900 px-6 py-12 sm:px-12 sm:py-14">
          {/* Soft light shapes for depth; purely decorative. */}
          <span aria-hidden className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/5" />
          <span aria-hidden className="absolute -bottom-32 right-40 h-64 w-64 rounded-full bg-white/5" />
          <div className="relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <h2 id="cta-title" className="text-balance text-2xl text-white sm:text-3xl">
                {t("cta.title")}
              </h2>
              <p className="mt-3 text-lg text-white/80">{t("cta.body")}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-3">
              <Button size="xl" variant="inverse" asChild>
                <Link href="/advisor">
                  {t("hero.ctaAdvisor")}
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </Button>
              <Button size="xl" variant="outline-inverse" asChild>
                <Link href="/chat">
                  <MessageSquare className="h-4 w-4" aria-hidden />
                  {t("hero.ctaChat")}
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
