"use client";

import { Leaf } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useApiHealth } from "@/lib/health";

export function SiteFooter() {
  const t = useTranslations("footer");
  const tc = useTranslations("common");
  const health = useApiHealth();
  return (
    <footer className="no-print mt-12 border-t border-border bg-surface pb-[calc(var(--bottombar-h)+1rem)] md:pb-0">
      <div className="mx-auto grid max-w-content gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <p className="inline-flex items-center gap-2 text-base font-semibold text-text">
            <span className="flex h-7 w-7 items-center justify-center rounded-control bg-primary text-primary-fg">
              <Leaf className="h-3.5 w-3.5" aria-hidden />
            </span>
            {tc("appName")}
          </p>
          <p className="mt-3 max-w-md text-sm text-muted">{t("attribution")}</p>
          <p className="mt-3 max-w-md text-sm text-muted">{t("disclaimer")}</p>
        </div>
        <div className="text-sm">
          <p className="font-semibold text-text">{t("method")}</p>
          <ul className="mt-3 space-y-2">
            <li><Link href="/about" className="text-muted hover:text-text">{t("sources")}</Link></li>
            <li><Link href="/about#confidence" className="text-muted hover:text-text">{t("method")}</Link></li>
            <li><Link href="/about#licence" className="text-muted hover:text-text">{t("licence")}</Link></li>
          </ul>
        </div>
        <div className="text-sm text-muted">
          <p className="tabular">{health.version ? t("version", { version: health.version }) : t("versionUnknown")}</p>
          <p className="mt-2">{t("rights", { year: new Date().getFullYear() })}</p>
        </div>
      </div>
    </footer>
  );
}
