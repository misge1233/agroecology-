import type { ChatSlotsHint, IndicatorMeta, RecommendQuery } from "./types";
import { familyName, indicatorLabel } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";

/**
 * Quick-reply protocol (U2). A chip sends a short sentence in the UI language
 * (the user sees it as their own message) AND a structured hint with the
 * canonical data-contract values, so the backend never guesses from a
 * translated sentence. English sentences stay word-for-word what the rule
 * parser has read since P5.
 */
export type ProtocolKey =
  | "protocol.farmAt"
  | "protocol.challenge"
  | "protocol.objective"
  | "protocol.challengeNote"
  | "protocol.objectiveNote";
/** A `useTranslations("chat")` translator (or a createTranslator equivalent). */
export type ProtocolT = (key: ProtocolKey, values?: Record<string, string | number>) => string;

export interface ProtocolMessage {
  text: string;
  hint: ChatSlotsHint;
}

export function challengeMessage(t: ProtocolT, locale: Locale, family: string): ProtocolMessage {
  return { text: t("protocol.challenge", { family: familyName(family, locale) }), hint: { practice_family: family } };
}

export function objectiveMessage(
  t: ProtocolT,
  locale: Locale,
  indicator: IndicatorMeta | { key: string; label: string }
): ProtocolMessage {
  // English keeps the API label in lower case (what the parser expects);
  // other languages use the glossary label, which contains the catalog noun.
  const objective = locale === "en" ? indicator.label.toLowerCase() : indicatorLabel(indicator.key, locale);
  return { text: t("protocol.objective", { objective }), hint: { indicator: indicator.key } };
}

export function locationMessage(
  t: ProtocolT,
  locale: Locale,
  lat: number,
  lon: number,
  pending: { family?: string | null; indicator?: IndicatorMeta | null }
): ProtocolMessage {
  const bits = [t("protocol.farmAt", { lat: lat.toFixed(4), lon: lon.toFixed(4) })];
  const hint: ChatSlotsHint = { lat, lon };
  if (pending.family) {
    bits.push(t("protocol.challengeNote", { family: familyName(pending.family, locale) }));
    hint.practice_family = pending.family;
  }
  if (pending.indicator) {
    const objective =
      locale === "en" ? pending.indicator.label.toLowerCase() : indicatorLabel(pending.indicator.key, locale);
    bits.push(t("protocol.objectiveNote", { objective }));
    hint.indicator = pending.indicator.key;
  }
  return { text: bits.join(" "), hint };
}

/** Deep link to the Advisor for a scored query ("Open in Advisor"). */
export function advisorQuery(q: RecommendQuery, topN: number): Record<string, string> {
  const out: Record<string, string> = {
    lat: String(q.lat),
    lon: String(q.lon),
    family: q.practice_family,
    indicator: q.indicator,
  };
  if (q.crop_type) out.crop = q.crop_type;
  if (topN !== 1) out.top = String(topN);
  return out;
}
