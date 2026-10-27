import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold leading-5 whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "bg-surface-2 text-text",
        primary: "bg-primary text-primary-fg",
        secondary: "bg-secondary text-secondary-fg",
        accent: "bg-accent text-accent-fg",
        // Medium confidence: amber fill with DARK text (6.24:1), never amber text.
        warning: "bg-warning text-[#0F1613]",
        danger: "bg-danger text-white",
        "outline-primary": "border border-primary text-primary",
        "outline-accent": "border border-accent text-accent-text",
        "outline-secondary": "border border-secondary text-secondary-text",
        "outline-neutral": "border border-border text-muted",
      },
    },
    defaultVariants: { variant: "neutral" },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** Confidence → badge variant. Low is NEUTRAL ("thin evidence"), never danger. */
export function confidenceVariant(level: "high" | "medium" | "low"): BadgeProps["variant"] {
  if (level === "high") return "primary";
  if (level === "medium") return "warning";
  return "neutral";
}

/** Tier → outline badge variant (evidence green, guidance sky, practice record ochre). */
export function tierVariant(tier: "evidence" | "guidance" | "practice"): BadgeProps["variant"] {
  if (tier === "guidance") return "outline-accent";
  if (tier === "practice") return "outline-secondary";
  return "outline-primary";
}
