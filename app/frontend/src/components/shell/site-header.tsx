"use client";

import { Suspense, useEffect, useState } from "react";
import { ArrowRight, Leaf, Menu, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "./language-switcher";
import { ThemeToggle } from "./theme-toggle";
import { NAV_ITEMS, isActive } from "./nav-items";

/** Wordmark: leaf tile + product name. Shared by the header and footer. */
export function BrandMark({ className, tileClassName }: { className?: string; tileClassName?: string }) {
  const t = useTranslations("common");
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-control bg-primary text-primary-fg",
          tileClassName
        )}
      >
        <Leaf className="h-[1.125rem] w-[1.125rem]" aria-hidden />
      </span>
      <span className="truncate text-[1.0625rem] font-semibold tracking-tight">{t("appName")}</span>
    </span>
  );
}

export function SiteHeader() {
  const t = useTranslations();
  const pathname = usePathname();
  // The phone menu remembers the path it was opened on, so navigating closes it
  // without a state-syncing effect. Escape closes it too.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenOn(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className="no-print sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur-md">
      <div className="container-page flex h-[var(--header-h)] items-center gap-4">
        <Link href="/" className="min-w-0 rounded-control text-text" aria-label={t("nav.home")}>
          <BrandMark />
        </Link>

        <nav aria-label={t("nav.main")} className="ml-6 hidden h-full items-stretch gap-1 md:flex">
          {NAV_ITEMS.map(({ href, key }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative inline-flex items-center px-3 text-[0.9375rem] font-medium transition-colors duration-base",
                  "after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors after:duration-base",
                  active ? "text-primary after:bg-primary" : "text-muted after:bg-transparent hover:text-text"
                )}
              >
                {t(`nav.${key}`)}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {/* useSearchParams (query preserved on switch) needs a Suspense boundary for static pages. */}
          <Suspense fallback={<div className="h-9 w-10 sm:w-[8.5rem]" aria-hidden />}>
            <LanguageSwitcher />
          </Suspense>
          <ThemeToggle />
          <Button size="sm" asChild className="ml-2 hidden lg:inline-flex">
            <Link href="/advisor">
              {t("nav.cta")}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={t("common.menu")}
            onClick={() => setOpenOn(open ? null : pathname)}
          >
            {open ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
          </Button>
        </div>
      </div>

      {/* Phone navigation: a plain disclosure panel under the header bar. */}
      <nav
        id="mobile-nav"
        aria-label={t("nav.main")}
        hidden={!open}
        className="border-t border-border bg-surface md:hidden"
      >
        <ul className="container-page space-y-1 py-3">
          {NAV_ITEMS.map(({ href, key, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-control px-3 py-3 text-base font-medium",
                    active ? "bg-primary-soft text-primary" : "text-text hover:bg-surface-2"
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden />
                  {t(`nav.${key}`)}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
