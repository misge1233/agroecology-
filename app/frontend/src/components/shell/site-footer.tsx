"use client";

import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { useApiHealth } from "@/lib/health";
import { BrandMark } from "./site-header";
import { NAV_ITEMS } from "./nav-items";

const linkClass = "text-band-muted transition-colors duration-base hover:text-band-fg";

export function SiteFooter() {
  const t = useTranslations("footer");
  const tn = useTranslations("nav");
  const health = useApiHealth();
  const pathname = usePathname();
  // The chat is a full-height app view; a footer under it would only scroll into view by accident.
  if (pathname === "/chat") return null;

  return (
    <footer className="no-print mt-auto bg-band text-band-fg">
      <div className="container-page grid grid-cols-2 gap-10 py-14 md:grid-cols-12">
        <div className="col-span-2 md:col-span-6 lg:col-span-5">
          <BrandMark className="text-band-fg" tileClassName="bg-white/10 text-band-fg" />
          <p className="mt-4 max-w-md text-sm leading-relaxed text-band-muted">{t("attribution")}</p>
        </div>

        <div className="md:col-span-3 lg:col-start-8 lg:col-span-2">
          <h2 className="text-sm font-semibold text-band-fg">{t("explore")}</h2>
          <ul className="mt-4 space-y-3 text-sm">
            {NAV_ITEMS.map(({ href, key }) => (
              <li key={href}>
                <Link href={href} className={linkClass}>
                  {tn(key)}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="md:col-span-3">
          <h2 className="text-sm font-semibold text-band-fg">{t("resources")}</h2>
          <ul className="mt-4 space-y-3 text-sm">
            <li><Link href="/about#sources" className={linkClass}>{t("sources")}</Link></li>
            <li><Link href="/about#confidence" className={linkClass}>{t("method")}</Link></li>
            <li><Link href="/about#contact" className={linkClass}>{t("contact")}</Link></li>
          </ul>
        </div>
      </div>

      <div className="border-t border-white/10">
        <div className="container-page flex flex-col gap-3 py-6 text-xs text-band-muted md:flex-row md:items-start md:justify-between md:gap-10">
          <p className="max-w-2xl leading-relaxed">{t("disclaimer")}</p>
          <p className="shrink-0 tabular">
            {t("rights", { year: new Date().getFullYear() })}
            <span className="mx-2" aria-hidden>·</span>
            {health.version ? t("version", { version: health.version }) : t("versionUnknown")}
          </p>
        </div>
      </div>
    </footer>
  );
}
