"use client";

import { Suspense } from "react";
import { Leaf } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeToggle } from "./theme-toggle";
import { NAV_ITEMS } from "./nav-items";

export function SiteHeader() {
  const t = useTranslations();
  const pathname = usePathname();
  return (
    <header className="no-print sticky top-0 z-40 border-b border-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex h-[var(--header-h)] max-w-content items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/" className="flex min-w-0 items-center gap-2.5 rounded-control">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-primary text-primary-fg">
            <Leaf className="h-4 w-4" aria-hidden />
          </span>
          <span className="flex min-w-0 flex-col leading-none">
            <span className="truncate text-base font-semibold tracking-tight text-text">{t("common.appName")}</span>
            <span className="mt-0.5 hidden text-xs text-muted sm:block">{t("common.tagline")}</span>
          </span>
        </Link>

        <nav aria-label={t("nav.main")} className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map(({ href, key }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-control px-3 py-2 text-sm font-medium transition-colors duration-base",
                  active ? "bg-primary-soft text-primary" : "text-muted hover:bg-surface-2 hover:text-text"
                )}
              >
                {t(`nav.${key}`)}
              </Link>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center gap-1.5">
          {/* useSearchParams (query preserved on switch) needs a Suspense boundary for static pages. */}
          <Suspense fallback={<div className="h-9 w-[8.5rem]" aria-hidden />}>
            <LanguageSwitcher />
          </Suspense>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
