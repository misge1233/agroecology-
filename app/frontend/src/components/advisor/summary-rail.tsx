"use client";

import { Pencil, RotateCcw } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { aezName, familyShort, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { StepKey } from "./advisor-state";

export function SummaryRail({
  lat,
  lon,
  belt,
  family,
  indicator,
  crop,
  onEdit,
  onReset,
  className,
}: {
  lat: number | null;
  lon: number | null;
  belt: string | null;
  family: string | null;
  indicator: string | null;
  crop: string | null;
  onEdit: (step: StepKey) => void;
  onReset: () => void;
  className?: string;
}) {
  const t = useTranslations("advisor.summary");
  const ts = useTranslations("advisor.steps");
  const tl = useTranslations("advisor.location");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const fmt = (n: number) => format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 4 });

  const rows: { step: StepKey; label: string; value: string | null; extra?: string | null }[] = [
    {
      step: "location",
      label: t("location"),
      value: lat != null && lon != null ? tl("pinAt", { lat: fmt(lat), lon: fmt(lon) }) : null,
      extra: belt ? `${t("belt")}: ${aezName(belt, locale)}` : null,
    },
    { step: "challenge", label: t("challenge"), value: family ? familyShort(family, locale) : null },
    { step: "objective", label: t("objective"), value: indicator ? indicatorLabel(indicator, locale) : null },
    { step: "crop", label: t("crop"), value: crop ? crop : indicator ? t("anyCrop") : null },
  ];
  const anySet = lat != null || !!family || !!indicator || !!crop;

  return (
    <aside aria-label={t("title")} className={className}>
      <Card className="p-4">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{t("title")}</p>
        <ul className="mt-3 divide-y divide-border">
          {rows.map((row) => (
            <li key={row.step} className="flex items-start justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-xs text-muted">{row.label}</p>
                <p className={row.value ? "text-sm font-medium text-text" : "text-sm text-muted"}>
                  {row.value ?? t("notSet")}
                </p>
                {row.extra ? <p className="text-xs text-muted">{row.extra}</p> : null}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 shrink-0 px-2"
                onClick={() => onEdit(row.step)}
                aria-label={t("edit", { step: ts(row.step) })}
              >
                <Pencil className="h-3.5 w-3.5" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
        {anySet ? (
          <Button variant="link" size="sm" className="mt-2 text-muted" onClick={onReset}>
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            {t("startOver")}
          </Button>
        ) : null}
      </Card>
    </aside>
  );
}
