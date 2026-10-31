import type { Metadata } from "next";
import localFont from "next/font/local";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { routing, LOCALE_META, type Locale } from "@/i18n/routing";
import { SHELL_NAMESPACES, pickMessages } from "@/i18n/messages";
import { MetadataProvider } from "@/components/metadata-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { THEME_INIT_SCRIPT } from "@/lib/theme-script";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { SiteHeader } from "@/components/shell/site-header";
import { SiteFooter } from "@/components/shell/site-footer";
import { ApiStatusBanner } from "@/components/shell/api-status-banner";
import { SkipLink } from "@/components/shell/skip-link";
import "../globals.css";

// Both faces are self-hosted (U2 0c): a production build must never depend on
// reaching Google Fonts (CI, air-gapped and low-connectivity deployments), and
// next/font/local sidesteps the Turbopack Google-font loader met in U1.
// IBM Plex Sans is the variable latin cut (wght 100–700; we use 400–600) plus
// its italic; SIL OFL — see src/app/fonts/README.md and LICENSE-IBMPlexSans.txt.
const sans = localFont({
  src: [
    { path: "../fonts/IBMPlexSans-latin.woff2", weight: "400 600", style: "normal" },
    { path: "../fonts/IBMPlexSans-latin-italic.woff2", weight: "400 600", style: "italic" },
  ],
  variable: "--font-sans",
  display: "swap",
  fallback: ["system-ui", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
});

// Noto Sans Ethiopic (variable 400–600, ethiopic subset), SIL OFL. Only
// referenced under html[lang="am"]; the unicode-range keeps Latin glyphs and
// digits on IBM Plex Sans (tabular numerals).
const ethiopic = localFont({
  src: "../fonts/NotoSansEthiopic-ethiopic.woff2",
  variable: "--font-ethiopic",
  weight: "400 600",
  display: "swap",
  preload: false,
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+030E, U+1200-1399, U+2D80-2DDE, U+AB01-AB2E, U+1E7E0-1E7E6, U+1E7E8-1E7EB, U+1E7ED-1E7EE, U+1E7F0-1E7FE",
    },
  ],
});

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "home.hero" });
  const tc = await getTranslations({ locale, namespace: "common" });
  return {
    title: { default: `${tc("appName")} — ${tc("tagline")}`, template: `%s · ${tc("appName")}` },
    description: t("subtitle"),
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const meta = LOCALE_META[locale as Locale];
  const tc = await getTranslations({ locale, namespace: "common" });
  // Only the shell's namespaces travel to the client here; pages add their own.
  const shellMessages = pickMessages(await getMessages(), SHELL_NAMESPACES);

  return (
    <html
      lang={meta.lang}
      suppressHydrationWarning
      className={meta.ethiopic ? `${sans.variable} ${ethiopic.variable}` : sans.variable}
    >
      <head>
        {/* Applies the stored theme before first paint. A plain server-rendered
            <script> (U6): React hydrates it but never creates it on the client,
            which is what React 19.2 warns about for next/script in a component. */}
        <script id="theme-init" suppressHydrationWarning dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="flex flex-col font-sans antialiased" suppressHydrationWarning>
        <NextIntlClientProvider messages={shellMessages}>
          <ThemeProvider>
            <TooltipProvider delayDuration={200}>
              <ToastProvider closeLabel={tc("close")}>
                <MetadataProvider>
                  <SkipLink />
                  <ApiStatusBanner />
                  <SiteHeader />
                  <main id="main" className="flex-1 print:min-h-0">
                    {children}
                  </main>
                  <SiteFooter />
                </MetadataProvider>
              </ToastProvider>
            </TooltipProvider>
          </ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
