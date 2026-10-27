import { ListOrdered, MapPinned, Target } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";

const STEPS = [
  { key: "location", icon: MapPinned },
  { key: "goal", icon: Target },
  { key: "results", icon: ListOrdered },
] as const;

export function HomeHow() {
  const t = useTranslations("home.how");
  return (
    <section className="mx-auto max-w-content px-4 py-10 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("eyebrow")}</p>
      <h2 className="mt-2 text-2xl">{t("title")}</h2>
      <ol className="mt-6 grid gap-4 md:grid-cols-3">
        {STEPS.map(({ key, icon: Icon }, i) => (
          <li key={key}>
            <Card className="h-full">
              <CardContent className="p-5 sm:p-5">
                <div className="flex items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-control bg-primary-soft text-primary">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="text-2xl font-semibold tabular text-muted" aria-hidden>
                    0{i + 1}
                  </span>
                </div>
                <h3 className="mt-4 text-lg">{t(`steps.${key}.title`)}</h3>
                <p className="mt-2 text-sm text-muted">{t(`steps.${key}.body`)}</p>
              </CardContent>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}
