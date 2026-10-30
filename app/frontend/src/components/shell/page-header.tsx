import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The title band every inner page opens with (U3): a soft band, an optional
 * eyebrow, the page's h1 and one lead sentence. Server- and client-safe.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  children,
  className,
  compact = false,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  className?: string;
  /** Tighter band for task pages (Advisor) where the work starts right below. */
  compact?: boolean;
}) {
  return (
    <section className={cn("no-print border-b border-border bg-surface-2", className)}>
      <div className={cn("container-page", compact ? "py-8 sm:py-10" : "py-12 sm:py-16")}>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1
          className={cn(
            "text-balance",
            compact ? "text-2xl sm:text-3xl" : "text-3xl sm:text-4xl",
            eyebrow ? "mt-3" : null
          )}
        >
          {title}
        </h1>
        {description ? (
          <p className={cn("max-w-3xl text-muted", compact ? "mt-2 text-base" : "mt-4 text-lg")}>{description}</p>
        ) : null}
        {children}
      </div>
    </section>
  );
}
