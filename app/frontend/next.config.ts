import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl (U1): the plugin wires src/i18n/request.ts into every server
// render so `useTranslations` / `getTranslations` resolve the [locale] segment.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    // The 55 practice images ship as WebP already; keep Next from re-encoding
    // to AVIF on the fly (slow on the small server this deploys to).
    formats: ["image/webp"],
  },
};

export default withNextIntl(nextConfig);
