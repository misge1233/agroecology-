"use client";

import { Languages } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { getPathname, usePathname } from "@/i18n/navigation";
import { LOCALES, LOCALE_NAMES, type Locale } from "@/i18n/routing";
import { hardNavigate } from "@/lib/hard-navigate";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Switches /[locale] while preserving the current route AND query string.
 * A full navigation (U6), not a client transition: see hard-navigate.ts.
 */
export function LanguageSwitcher({ className }: { className?: string }) {
  const t = useTranslations("nav.language");
  const locale = useLocale() as Locale;
  const pathname = usePathname();
  const search = useSearchParams();

  function change(next: string) {
    if (next === locale) return;
    const query = search.toString();
    const path = getPathname({ href: pathname, locale: next as Locale });
    hardNavigate(query ? `${path}?${query}` : path);
  }

  return (
    <div className={className}>
      <Select value={locale} onValueChange={change}>
        {/* Icon-only on phones (0a: the full trigger pushed the header past 390 px). */}
        <SelectTrigger aria-label={t("change")} className="h-9 w-10 justify-center gap-2 px-0 sm:w-auto sm:min-w-[8.5rem] sm:justify-between sm:px-3 [&>svg:last-child]:hidden sm:[&>svg:last-child]:block">
          <Languages className="h-4 w-4 shrink-0 text-muted" aria-hidden />
          <span className="hidden truncate sm:inline">
            <SelectValue />
          </span>
        </SelectTrigger>
        <SelectContent>
          {LOCALES.map((l) => (
            <SelectItem key={l} value={l} lang={l}>
              {LOCALE_NAMES[l]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <span className="sr-only">{t("current", { name: LOCALE_NAMES[locale] })}</span>
    </div>
  );
}
