"use client";

import { useTranslations } from "next-intl";

export function SkipLink() {
  const t = useTranslations("common");
  return (
    <a
      href="#main"
      className="no-print sr-only-focusable absolute left-4 top-4 z-50 rounded-control bg-primary px-3 py-2 text-sm font-semibold text-primary-fg"
    >
      {t("skipToContent")}
    </a>
  );
}
