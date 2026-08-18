import type { Metadata } from "next";
import { IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { MetadataProvider } from "@/components/metadata-provider";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

const sans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const display = Source_Serif_4({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Agroecology AI — CSA Practice Recommender",
  description:
    "Evidence-ranked climate-smart agriculture recommendations for Ethiopia — geospatial context, field-trial evidence, and transparent confidence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${sans.variable} ${display.variable} font-sans antialiased`}
        suppressHydrationWarning
      >
        <ThemeProvider>
          <MetadataProvider>
            <SiteHeader />
            <main>{children}</main>
          </MetadataProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
