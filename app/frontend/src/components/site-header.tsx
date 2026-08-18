"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Leaf, Menu, Moon, Sun, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "./theme-provider";
import { Button } from "./ui/button";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/chat", label: "Chatbot" },
  { href: "/dashboard", label: "Dashboard" },
];

function isNavActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function SiteHeader() {
  const pathname = usePathname();
  const { theme, toggle, ready } = useTheme();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50">
      <div className="bg-header-surface border-b border-leaf/15 shadow-[0_1px_0_rgb(255_255_255/0.55)_inset]">
        <div className="mx-auto flex h-[var(--header-h)] max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5"
            onClick={() => setOpen(false)}
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-leaf text-white shadow-sm transition duration-200 group-hover:bg-leaf-deep">
              <Leaf className="h-4 w-4" aria-hidden />
            </span>
            <span className="flex flex-col leading-none">
              <span className="font-display text-[1.2rem] font-semibold tracking-tight text-ink sm:text-[1.3rem]">
                AgroAdvisor-ET
              </span>
              <span className="mt-1 hidden text-[10px] font-medium uppercase tracking-[0.14em] text-mute sm:block">
                Agroecology+ decision support
              </span>
            </span>
          </Link>

          <nav className="hidden items-stretch gap-1 self-stretch md:flex" aria-label="Main">
            {NAV.map(({ href, label }) => {
              const active = isNavActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "inline-flex items-center border-b-[3px] px-4 text-[17px] font-semibold tracking-tight transition duration-200 sm:text-[18px]",
                    active
                      ? "border-leaf text-leaf-deep dark:text-leaf-bright"
                      : "border-transparent text-ink/70 hover:text-ink"
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-1.5 sm:gap-2">
            <button
              type="button"
              onClick={toggle}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-mute transition duration-200 hover:bg-white/70 hover:text-ink focus-ring dark:hover:bg-white/10"
              aria-label={
                ready && theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              {ready && theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </button>
            <Button
              href="/chat"
              variant="primary"
              size="md"
              className="hidden sm:inline-flex"
            >
              Request recommendation
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Button>
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-lg text-ink transition duration-200 hover:bg-white/70 md:hidden dark:hover:bg-white/10"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {open && (
          <div className="border-t border-leaf/15 px-4 py-4 md:hidden">
            <nav className="flex flex-col gap-1" aria-label="Mobile">
              {NAV.map(({ href, label }) => {
                const active = isNavActive(pathname, href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "rounded-xl px-3.5 py-3 text-lg font-semibold transition",
                      active
                        ? "bg-white/80 text-leaf-deep dark:bg-white/10 dark:text-leaf-bright"
                        : "text-ink hover:bg-white/60 dark:hover:bg-white/10"
                    )}
                  >
                    {label}
                  </Link>
                );
              })}
              <Button
                href="/chat"
                variant="primary"
                size="lg"
                className="mt-2 w-full"
              >
                Request recommendation
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Button>
            </nav>
          </div>
        )}
      </div>
    </header>
  );
}
