"use client";

import { WifiOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { checkHealth, useApiHealth } from "@/lib/health";
import { Button } from "@/components/ui/button";

/** Danger banner driven by /health — the one legitimate use of danger red. */
export function ApiStatusBanner() {
  const t = useTranslations("status");
  const health = useApiHealth();
  if (health.status !== "down") return null;
  return (
    <div
      role="alert"
      className="border-b border-danger/40 bg-danger-soft px-4 py-2 text-sm text-text"
    >
      <div className="mx-auto flex max-w-content flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2">
          <WifiOff className="h-4 w-4 text-danger-text" aria-hidden />
          {t("apiUnreachable")}
        </span>
        <Button variant="outline" size="sm" onClick={() => void checkHealth()}>
          {t("retry")}
        </Button>
      </div>
    </div>
  );
}
