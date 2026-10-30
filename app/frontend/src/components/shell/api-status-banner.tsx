"use client";

import { Loader2, WifiOff } from "lucide-react";
import { useTranslations } from "next-intl";
import { checkHealth, useApiHealth } from "@/lib/health";
import { useRetrying } from "@/lib/retry-store";
import { Button } from "@/components/ui/button";

/** Danger banner driven by /health — the one legitimate use of danger red.
 *  Below it, a quiet strip while an API call is being retried (U2 item 5). */
export function ApiStatusBanner() {
  const t = useTranslations("status");
  const health = useApiHealth();
  const retrying = useRetrying();
  if (health.status !== "down") {
    if (!retrying) return null;
    return (
      <div role="status" className="no-print border-b border-warning/50 bg-warning-soft py-1.5 text-sm text-text">
        <div className="container-page flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-warning-text" aria-hidden />
          {t("retrying")}
        </div>
      </div>
    );
  }
  return (
    <div
      role="alert"
      className="no-print border-b border-danger/40 bg-danger-soft py-2 text-sm text-text"
    >
      <div className="container-page flex flex-wrap items-center justify-between gap-2">
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
