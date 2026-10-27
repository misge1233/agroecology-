"use client";

import { RouteError } from "@/components/shell/route-error";

export default function LocaleError(props: { error: Error & { digest?: string }; reset: () => void }) {
  return <RouteError {...props} />;
}
