"use client";

import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Shared step chrome (U5): every Advisor input step is one white panel with
 * the same heading scale, helper text and footer (Back left, primary right).
 */
export function StepPanel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-panel border border-border bg-surface p-5 shadow-1 sm:p-8", className)}>{children}</div>
  );
}

export function StepHeader({ title, help, step }: { title: string; help?: string; step?: string }) {
  return (
    <div className="mb-6 sm:mb-8">
      {step ? <p className="eyebrow">{step}</p> : null}
      <h2 id="advisor-step-title" className={cn("text-2xl", step ? "mt-2" : null)}>
        {title}
      </h2>
      {help ? <p className="mt-2 max-w-2xl text-base text-muted">{help}</p> : null}
    </div>
  );
}

export function StepFooter({ onBack, children }: { onBack?: () => void; children?: ReactNode }) {
  const tc = useTranslations("common");
  return (
    <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6">
      {onBack ? (
        <Button type="button" variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {tc("back")}
        </Button>
      ) : (
        <span aria-hidden />
      )}
      {children}
    </div>
  );
}
