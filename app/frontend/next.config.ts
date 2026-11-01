import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import pkg from "./package.json" with { type: "json" };

// next-intl (U1): the plugin wires src/i18n/request.ts into every server
// render so `useTranslations` / `getTranslations` resolve the [locale] segment.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // U9 (E): the build version for the footer and "How to cite", independent of the API.
  env: { NEXT_PUBLIC_APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION ?? pkg.version },
  // The floating dev-tools badge sits over page content; keep the dev view clean.
  devIndicators: false,
  images: {
    // The 55 practice images ship as WebP already; keep Next from re-encoding
    // to AVIF on the fly (slow on the small server this deploys to).
    formats: ["image/webp"],
  },
};

export default withNextIntl(nextConfig);
