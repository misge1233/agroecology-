"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
  icon?: ReactNode;
}

/** Selectable pill (aria-pressed). Use inside a group with role="group". */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { className, selected = false, icon, children, ...props },
  ref
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-pressed={selected}
      className={cn(
        "inline-flex min-h-10 items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors duration-base",
        selected
          ? "border-primary bg-primary-soft text-text"
          : "border-border bg-surface text-text hover:border-primary/50 hover:bg-surface-2",
        className
      )}
      {...props}
    >
      {selected ? <Check className="h-4 w-4 text-primary" aria-hidden /> : icon}
      {children}
    </button>
  );
});
