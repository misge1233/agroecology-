import { defineRouting } from "next-intl/routing";

/** The three UI languages (U1). Order = order in the language switcher. */
export const LOCALES = ["en", "am", "om"] as const;
export type Locale = (typeof LOCALES)[number];

/** Human names in each language's own script, for the switcher. */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  am: "አማርኛ",
  om: "Afaan Oromoo",
};

/** `lang` attribute values and whether the script needs the Ethiopic font. */
export const LOCALE_META: Record<Locale, { lang: string; ethiopic: boolean }> = {
  en: { lang: "en", ethiopic: false },
  am: { lang: "am", ethiopic: true },
  om: { lang: "om", ethiopic: false },
};

export const routing = defineRouting({
  locales: LOCALES,
  defaultLocale: "en",
  // /en, /am, /om — always prefixed so a shared link carries its language.
  localePrefix: "always",
  // Detection order in the proxy: this cookie → Accept-Language → "en".
  localeCookie: { name: "agro-locale", maxAge: 60 * 60 * 24 * 365 },
});

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}
