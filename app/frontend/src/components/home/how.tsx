import { ListOrdered, MapPinned, Target } from "lucide-react";
import { useTranslations } from "next-intl";

const STEPS = [
  { key: "location", icon: MapPinned },
  { key: "goal", icon: Target },
  { key: "results", icon: ListOrdered },
] as const;

export function HomeHow() {
  const t = useTranslations("home.how");
  return (
    <section aria-labelledby="how-title" className="py-20 sm:py-24">
      <div className="container-page">
        <div className="mx-auto max-w-2xl text-center">
          <p className="eyebrow">{t("eyebrow")}</p>
          <h2 id="how-title" className="mt-3 text-balance text-3xl">
            {t("title")}
          </h2>
        </div>
        <ol className="relative mt-14 grid gap-10 md:grid-cols-3 md:gap-8">
          {/* Connector line behind the step badges (desktop only). */}
          <span aria-hidden className="absolute left-[16.7%] right-[16.7%] top-7 hidden h-px bg-border md:block" />
          {STEPS.map(({ key, icon: Icon }, i) => (
            <li key={key} className="relative flex flex-col items-center text-center">
              <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-fg shadow-1 ring-8 ring-background">
                <Icon className="h-6 w-6" aria-hidden />
                <span className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-surface text-xs font-semibold tabular text-primary ring-1 ring-border" aria-hidden>
                  {i + 1}
                </span>
              </span>
              <h3 className="mt-6 text-lg">{t(`steps.${key}.title`)}</h3>
              <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{t(`steps.${key}.body`)}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
