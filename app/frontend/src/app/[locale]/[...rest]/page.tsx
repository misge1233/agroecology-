import { notFound } from "next/navigation";

/** Any unmatched path inside a locale renders the locale's not-found page. */
export default function CatchAll() {
  notFound();
}
