"use client";

import Link from "next/link";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "dark" | "secondary" | "ghost" | "gradient";
type Size = "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:
    "bg-leaf text-white hover:bg-leaf-deep shadow-soft",
  dark: "bg-ink text-elevated hover:bg-ink/90 shadow-soft",
  secondary:
    "border border-edge bg-elevated text-ink hover:bg-panel shadow-sm",
  ghost: "text-ink hover:bg-panel",
  gradient:
    "bg-brand-gradient text-white shadow-soft hover:opacity-95",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-3.5 text-[13px]",
  md: "h-10 px-5 text-sm",
  lg: "h-11 px-5 text-[15px]",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  href?: string;
  children: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "primary",
      size = "md",
      href,
      children,
      type = "button",
      ...props
    },
    ref
  ) {
    const classes = cn(
      "inline-flex items-center justify-center gap-2 rounded-xl font-semibold tracking-tight transition focus-ring disabled:pointer-events-none disabled:opacity-40",
      variants[variant],
      sizes[size],
      className
    );

    if (href) {
      return (
        <Link href={href} className={classes}>
          {children}
        </Link>
      );
    }

    return (
      <button ref={ref} type={type} className={classes} {...props}>
        {children}
      </button>
    );
  }
);
