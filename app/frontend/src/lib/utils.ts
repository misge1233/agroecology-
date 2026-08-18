import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** True when the pct_change is beneficial given the goal direction.
 *  "increase" goals want a positive change; "reduce" goals want a negative one. */
export function isBeneficial(
  pctChange: number,
  direction: string
): boolean {
  if (direction === "reduce" || direction === "lower_is_better") {
    return pctChange <= 0;
  }
  return pctChange >= 0;
}

export function formatPct(pct: number): string {
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}
