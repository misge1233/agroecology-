"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/** Shared body for every route-level error boundary. */
export function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const t = useTranslations("errors");
  return (
    <div className="mx-auto max-w-xl px-4 py-16 sm:px-6">
      <Alert variant="danger" title={t("title")}>
        {t("body")}
      </Alert>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={reset}>{t("retry")}</Button>
        <Button variant="outline" asChild>
          <Link href="/">{t("home")}</Link>
        </Button>
      </div>
      {error.digest ? (
        <p className="mt-4 text-xs text-muted">
          {t("details")}: <code className="tabular">{error.digest}</code>
        </p>
      ) : null}
    </div>
  );
}
