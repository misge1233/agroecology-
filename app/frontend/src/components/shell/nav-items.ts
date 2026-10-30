import { Compass, Home, Info, MessageSquare, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: "/" | "/advisor" | "/chat" | "/about";
  key: "home" | "advisor" | "chat" | "about";
  icon: LucideIcon;
}

/** The four top-level pages, in header order (U3). */
export const NAV_ITEMS: NavItem[] = [
  { href: "/", key: "home", icon: Home },
  { href: "/advisor", key: "advisor", icon: Compass },
  { href: "/chat", key: "chat", icon: MessageSquare },
  { href: "/about", key: "about", icon: Info },
];

/** Home matches only itself; every other item also matches its sub-routes. */
export function isActive(pathname: string, href: NavItem["href"]): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
