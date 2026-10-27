import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

/** Server-side message loading for the [locale] segment (next-intl). */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    // Western digits everywhere, including Amharic (the API's numbers are
    // ASCII and the explanation guardrail matches \d).
    formats: {
      number: { plain: { maximumFractionDigits: 1 } },
    },
  };
});
