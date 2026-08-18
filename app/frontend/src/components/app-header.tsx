"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Leaf, LayoutDashboard, MessageSquare, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme } from "./theme-provider";
import { AboutPopover } from "./about-popover";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
];

export function AppHeader() {
  const pathname = usePathname();
  const { theme, toggle, ready } = useTheme();

  return (
    <header className="sticky top-0 z-40">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-4 sm:px-6 xl:max-w-6xl 2xl:max-w-7xl 2xl:px-8">
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-2xl bg-leaf text-white shadow-soft transition group-hover:scale-[1.03] 2xl:h-10 2xl:w-10">
            <Leaf className="relative h-4 w-4 2xl:h-[18px] 2xl:w-[18px]" />
          </span>
          <span className="font-display text-[1.35rem] leading-none tracking-tight text-ink 2xl:text-[1.6rem]">
            AgroGuide
          </span>
        </Link>

        <nav
          className="glass flex items-center gap-0.5 rounded-full border border-edge/80 p-1 shadow-soft"
          aria-label="Main"
        >
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[13px] font-medium transition 2xl:px-4 2xl:py-2 2xl:text-[15px]",
                  active
                    ? "bg-leaf text-white shadow-sm"
                    : "text-mute hover:text-ink"
                )}
              >
                <Icon className="h-3.5 w-3.5 2xl:h-4 2xl:w-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-0.5">
          <AboutPopover />
          <button
            type="button"
            onClick={toggle}
            className="rounded-full p-2.5 text-mute transition hover:bg-panel hover:text-ink"
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
        </div>
      </div>
    </header>
  );
}
