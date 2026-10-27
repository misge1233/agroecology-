import { ArrowRight, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Button } from "@/components/ui/button";

export function HomeHero() {
  const t = useTranslations("home.hero");
  return (
    <section className="mx-auto max-w-content px-4 pb-10 pt-12 sm:px-6 sm:pt-16">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{t("eyebrow")}</p>
        <h1 className="mt-3 text-balance text-3xl sm:text-[2.75rem] sm:leading-[1.15]">{t("title")}</h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">{t("subtitle")}</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link href="/advisor">
              {t("ctaAdvisor")}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link href="/chat">
              <MessageSquare className="h-4 w-4" aria-hidden />
              {t("ctaChat")}
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
