"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepperStep {
  key: string;
  label: string;
  /** Can the user jump to this step? (completed or current) */
  reachable: boolean;
  complete: boolean;
}

/**
 * Horizontal progress stepper. Completed steps are buttons (jump back);
 * the current step carries aria-current="step".
 */
export function Stepper({
  steps,
  current,
  onSelect,
  label,
  currentLabel,
  completedLabel,
  className,
}: {
  steps: StepperStep[];
  current: string;
  onSelect: (key: string) => void;
  label: string;
  currentLabel: string;
  completedLabel: string;
  className?: string;
}) {
  return (
    <nav aria-label={label} className={cn("w-full", className)}>
      <ol className="flex items-center gap-1 sm:gap-2">
        {steps.map((step, i) => {
          const isCurrent = step.key === current;
          const content = (
            <>
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular",
                  isCurrent
                    ? "bg-primary text-primary-fg"
                    : step.complete
                      ? "bg-primary-soft text-primary"
                      : "bg-surface-2 text-muted"
                )}
                aria-hidden
              >
                {step.complete && !isCurrent ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span
                className={cn(
                  "hidden text-sm sm:inline",
                  isCurrent ? "font-semibold text-text" : "text-muted"
                )}
              >
                {step.label}
              </span>
              <span className="sr-only">
                {step.label}
                {isCurrent ? `, ${currentLabel}` : step.complete ? `, ${completedLabel}` : ""}
              </span>
            </>
          );
          return (
            <li key={step.key} className="flex min-w-0 items-center gap-1 sm:gap-2">
              {i > 0 ? (
                <span
                  className={cn("h-px w-4 sm:w-8", step.complete || isCurrent ? "bg-primary" : "bg-border")}
                  aria-hidden
                />
              ) : null}
              {step.reachable && !isCurrent ? (
                <button
                  type="button"
                  onClick={() => onSelect(step.key)}
                  className="flex items-center gap-2 rounded-control px-1 py-1 hover:bg-surface-2"
                >
                  {content}
                </button>
              ) : (
                <span
                  aria-current={isCurrent ? "step" : undefined}
                  className="flex items-center gap-2 px-1 py-1"
                >
                  {content}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
