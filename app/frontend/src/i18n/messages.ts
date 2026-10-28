import type { AbstractIntlMessages } from "next-intl";

/**
 * Per-route message splitting (U2 0d). The `[locale]` layout provides only the
 * shell namespaces to the client; each page re-provides the shell plus its own
 * namespaces (a nested NextIntlClientProvider REPLACES messages, so a page's
 * set must be a superset of what its client components read). Server
 * components keep using getTranslations with the full catalog.
 */
export const SHELL_NAMESPACES = ["common", "nav", "footer", "status", "errors", "a11y"] as const;
export const HOME_NAMESPACES = [...SHELL_NAMESPACES, "home"] as const;
export const ADVISOR_NAMESPACES = [...SHELL_NAMESPACES, "advisor", "evidence", "chat.protocol"] as const;
export const CHAT_NAMESPACES = [...SHELL_NAMESPACES, "chat", "advisor", "evidence"] as const;

/** Keep only the given namespaces ("a" or nested "a.b") of a message tree. */
export function pickMessages(messages: AbstractIntlMessages, namespaces: readonly string[]): AbstractIntlMessages {
  const out: AbstractIntlMessages = {};
  for (const ns of namespaces) {
    const parts = ns.split(".");
    let src: unknown = messages;
    for (const part of parts) {
      src = src && typeof src === "object" ? (src as Record<string, unknown>)[part] : undefined;
    }
    if (src === undefined) continue;
    let dst: Record<string, unknown> = out as Record<string, unknown>;
    for (const part of parts.slice(0, -1)) {
      dst[part] = dst[part] && typeof dst[part] === "object" ? dst[part] : {};
      dst = dst[part] as Record<string, unknown>;
    }
    dst[parts[parts.length - 1]] = src;
  }
  return out;
}
