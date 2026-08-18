"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

export function StatCounter({
  value,
  label,
  suffix = "",
  className,
}: {
  value: number;
  label: string;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(reduce ? value : 0);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setDisplay(value);
      return;
    }
    const duration = 1400;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(value * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, reduce]);

  return (
    <div ref={ref} className={cn("text-center", className)}>
      <p className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        {formatNumber(display)}
        {suffix}
      </p>
      <p className="mt-1.5 text-[13px] leading-snug text-mute">{label}</p>
    </div>
  );
}

export function Chip({
  children,
  active,
  onClick,
  className,
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  const Comp = onClick ? "button" : "span";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition",
        active
          ? "border-transparent bg-leaf text-white shadow-sm"
          : "border-edge bg-elevated text-mute shadow-sm hover:border-leaf/25 hover:text-ink",
        className
      )}
    >
      {children}
    </Comp>
  );
}

export function MarqueeRow({
  items,
  className,
  reverse,
  variant = "default",
  speedClass,
}: {
  items: string[];
  className?: string;
  reverse?: boolean;
  variant?: "default" | "glass";
  speedClass?: string;
}) {
  const doubled = [...items, ...items];
  const glass = variant === "glass";
  return (
    <div
      className={cn(
        "relative overflow-hidden py-3",
        !glass && "border-y border-edge/70 py-5",
        className
      )}
      aria-label="Features"
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 z-10 w-12 bg-gradient-to-r to-transparent sm:w-16",
          glass ? "from-transparent" : "from-canvas"
        )}
      />
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 right-0 z-10 w-12 bg-gradient-to-l to-transparent sm:w-16",
          glass ? "from-transparent" : "from-canvas"
        )}
      />
      <div
        className={cn(
          "flex w-max gap-2.5 pr-2.5 motion-reduce:animate-none sm:gap-3",
          reverse ? "animate-marquee-reverse" : "animate-marquee",
          speedClass
        )}
      >
        {doubled.map((item, i) => (
          <span
            key={`${item}-${i}`}
            className={cn(
              "inline-flex shrink-0 items-center rounded-full border px-3.5 py-1.5 text-[12.5px] font-medium shadow-sm sm:px-4 sm:py-2 sm:text-[13px]",
              glass
                ? "border-white/45 bg-white/85 text-ink backdrop-blur"
                : "border-edge bg-elevated/70 text-ink/80"
            )}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
