import type { Metadata } from "next";
import Script from "next/script";
import { IBM_Plex_Sans } from "next/font/google";
import localFont from "next/font/local";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing, LOCALE_META, type Locale } from "@/i18n/routing";
import { MetadataProvider } from "@/components/metadata-provider";
import { ThemeProvider, THEME_INIT_SCRIPT } from "@/components/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { SiteHeader } from "@/components/shell/site-header";
import { SiteFooter } from "@/components/shell/site-footer";
import { BottomTabBar } from "@/components/shell/bottom-tab-bar";
import { ApiStatusBanner } from "@/components/shell/api-status-banner";
import { SkipLink } from "@/components/shell/skip-link";
import "../globals.css";

const sans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

// Noto Sans Ethiopic (variable 400–600, ethiopic subset) is self-hosted: Turbopack's
// next/font/google loader rejects this family ("queries have exactly one entry"),
// which broke `next dev`. See src/app/fonts/README.md. Only referenced under
// html[lang="am"]; the unicode-range keeps Latin glyphs on IBM Plex Sans.
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

  return (
    <html
      lang={meta.lang}
      suppressHydrationWarning
      className={meta.ethiopic ? `${sans.variable} ${ethiopic.variable}` : sans.variable}
    >
      <body className="font-sans antialiased" suppressHydrationWarning>
        {/* Applies the stored theme before first paint. next/script keeps it out of
            React's hydration (a raw <script> in <head> hydrated inconsistently on
            streamed routes). */}
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        <NextIntlClientProvider>
          <ThemeProvider>
            <TooltipProvider delayDuration={200}>
              <ToastProvider closeLabel={tc("close")}>
                <MetadataProvider>
                  <SkipLink />
                  <ApiStatusBanner />
                  <SiteHeader />
                  <main id="main" className="min-h-[60dvh] pb-[var(--bottombar-h)] md:pb-0">
                    {children}
                  </main>
                  <SiteFooter />
                  <BottomTabBar />
                </MetadataProvider>
              </ToastProvider>
            </TooltipProvider>
          </ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
