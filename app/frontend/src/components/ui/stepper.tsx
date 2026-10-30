"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepperStep {
  key: string;
  label: string;
  /** Can the user jump to this step? (completed or current) */
  reachable: boolean;
  complete: boolean;
  /** What was chosen at this step, shown under the label (U5). */
  value?: string | null;
}

/**
 * Segmented progress stepper (U5): one column per step with a progress bar,
 * the step number, its label and the value chosen there. Completed steps are
 * buttons (jump back); the current step carries aria-current="step".
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
      <ol className="grid gap-2 sm:gap-4" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((step, i) => {
          const isCurrent = step.key === current;
          const done = step.complete && !isCurrent;
          const content = (
            <>
              <span
                aria-hidden
                className={cn(
                  "block h-1 w-full rounded-full transition-colors duration-base",
                  isCurrent || step.complete ? "bg-primary" : "bg-surface"
                )}
              />
              <span className="mt-3 flex min-w-0 items-start gap-2.5">
                <span
                  aria-hidden
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold tabular",
                    isCurrent
                      ? "bg-primary text-primary-fg shadow-1"
                      : done
                        ? "bg-surface text-primary ring-1 ring-primary"
                        : "bg-surface text-muted ring-1 ring-border"
                  )}
                >
                  {done ? <Check className="h-4 w-4" /> : i + 1}
                </span>
                <span aria-hidden className="hidden min-w-0 flex-col text-left md:flex">
                  <span className={cn("truncate text-sm", isCurrent ? "font-semibold text-text" : done ? "font-medium text-text" : "text-muted")}>
                    {step.label}
                  </span>
                  {step.value ? <span className="truncate text-xs text-muted">{step.value}</span> : null}
                </span>
              </span>
              <span className="sr-only">
                {step.label}
                {isCurrent ? `, ${currentLabel}` : step.complete ? `, ${completedLabel}` : ""}
                {step.value ? `: ${step.value}` : ""}
              </span>
            </>
          );
          return (
            <li key={step.key} className="min-w-0">
              {step.reachable && !isCurrent ? (
                <button
                  type="button"
                  onClick={() => onSelect(step.key)}
                  className="block w-full min-w-0 rounded-control pb-1 text-left transition-opacity duration-base hover:opacity-80"
                >
                  {content}
                </button>
              ) : (
                <span aria-current={isCurrent ? "step" : undefined} className="block min-w-0 pb-1">
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
