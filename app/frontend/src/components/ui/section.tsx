"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export function Reveal({
  children,
  className,
  delay = 0,
  y = 20,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
}) {
  const reduce = useReducedMotion();
  if (reduce) {
    return <div className={className}>{children}</div>;
  }
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </motion.div>
  );
}

export function Section({
  id,
  eyebrow,
  title,
  subtitle,
  children,
  className,
  narrow,
}: {
  id?: string;
  eyebrow?: string;
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
  narrow?: boolean;
}) {
  return (
    <section id={id} className={cn("relative py-16 sm:py-20", className)}>
      <div
        className={cn(
          "mx-auto px-4 sm:px-6",
          narrow ? "max-w-3xl" : "max-w-7xl"
        )}
      >
        {(eyebrow || title || subtitle) && (
          <Reveal className="mb-10 max-w-3xl sm:mb-12">
            {eyebrow && <p className="eyebrow mb-3">{eyebrow}</p>}
            {title && (
              <h2 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-[2.75rem] sm:leading-[1.12]">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-3 max-w-2xl text-base leading-relaxed text-mute sm:text-[1.05rem]">
                {subtitle}
              </p>
            )}
          </Reveal>
        )}
        {children}
      </div>
    </section>
  );
}

export function GlassCard({
  children,
  className,
  hover,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-edge bg-elevated shadow-soft",
        hover &&
          "transition duration-250 hover:border-leaf/20 hover:shadow-lift",
        className
      )}
    >
      {children}
    </div>
  );
}

export function GradientText({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <span className={cn("text-ink", className)}>{children}</span>;
}
