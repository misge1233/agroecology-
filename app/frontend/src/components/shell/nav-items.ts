import { Compass, Info, MessageSquare, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: "/advisor" | "/chat" | "/about";
  key: "advisor" | "chat" | "about";
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/advisor", key: "advisor", icon: Compass },
  { href: "/chat", key: "chat", icon: MessageSquare },
  { href: "/about", key: "about", icon: Info },
];
