import createMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";
import { routing } from "./i18n/routing";

/**
 * Locale routing (Next 16 `proxy`, formerly `middleware`).
 *
 * Every page lives under /[locale]; a request without a prefix is redirected
 * to the detected locale: the `agro-locale` cookie first, then
 * Accept-Language, then "en". API routes, Next internals and static files
 * are excluded by the matcher.
 */
const intl = createMiddleware(routing);

export function proxy(request: NextRequest) {
  return intl(request);
}

export default proxy;

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
