import type { IndicatorMeta, Metadata, RecommendQuery } from "./types";

export type ChatSetupStage = "challenge" | "objective" | "location" | "complete";

export type DashboardSetupStage = "location" | "challenge" | "objective" | "complete";

export interface ChatSetupState {
  stage: ChatSetupStage;
  family: string | null;
  indicatorKey: string | null;
  hasLocation: boolean;
  placeName?: string | null;
}

/** Server-extracted slots from the evidence-gated chat pipeline. */
export interface ChatSlotsPayload {
  practice_family?: string | null;
  indicator?: string | null;
  lat?: number | null;
  lon?: number | null;
  place_name?: string | null;
  crop_type?: string | null;
  missing?: string[];
  inferred?: string[];
  confidence?: Record<string, string>;
  is_followup?: boolean;
  wants_advice?: boolean;
  geocode_source?: string | null;
}

const CHALLENGE_PREFIX = /^my challenge is\s+/i;
const OBJECTIVE_PREFIX = /^my objective is to\s+/i;
const COORD_RE = /(-?\d+\.\d+)\s*[,;]\s*(-?\d+\.\d+)/;

const INDICATOR_PHRASES: { phrase: string; key: string }[] = [
  { phrase: "reduce soil loss", key: "soil loss" },
  { phrase: "soil loss", key: "soil loss" },
  { phrase: "soil erosion", key: "soil loss" },
  { phrase: "erosion", key: "soil loss" },
  { phrase: "reduce runoff", key: "runoff" },
  { phrase: "runoff", key: "runoff" },
  { phrase: "improve water use efficiency", key: "water use efficiency" },
  { phrase: "water use efficiency", key: "water use efficiency" },
  { phrase: "water efficiency", key: "water use efficiency" },
  { phrase: "improve soil organic matter", key: "SOM content" },
  { phrase: "soil organic matter", key: "SOM content" },
  { phrase: "soil health", key: "SOM content" },
  { phrase: "increase yield", key: "yield" },
  { phrase: "crop yield", key: "yield" },
  { phrase: "biomass", key: "biomass yield" },
  { phrase: "fodder", key: "biomass yield" },
  { phrase: "income", key: "income" },
  { phrase: "yield", key: "yield" },
];

function normMatch(text: string): string {
  return text
    .toLowerCase()
    .replace(/-/g, " ")
    .replace(/[/|,;:]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const FAMILY_HINTS: { re: RegExp; family: string }[] = [
  {
    re: /\b(erosion|soil loss|runoff|sloping|slope|terrace|contour|gully|bund)\b/i,
    family: "Erosion control and water management",
  },
  {
    re: /\b(livestock|cattle|fodder|forage|dairy|herd)\b/i,
    family: "Livestock production and management",
  },
  {
    re: /\b(fertilit|compost|manure|soil organic)\b/i,
    family: "Integrated soil fertility management",
  },
  {
    re: /\b(agro-?forest|tree|woodlot|forest management)\b/i,
    family: "Agro-forestry and forest management",
  },
  {
    re: /\b(crop production|intercrop|rotation)\b/i,
    family: "Crop production and management",
  },
];

/** Lightweight place-name cue (backend geocodes; UI only advances stage). */
const PLACE_HINT_RE =
  /\b(?:near|around|in|outside|close\s+to)\s+[A-Za-z][A-Za-z\s\-']{2,40}/i;

/** @deprecated Use metadata indicators_by_family; kept for offline fallback only. */
const QUICK_REPLY_EXCLUDE: Record<string, string[]> = {
  "Erosion control and water management": ["income"],
  "Agro-forestry and forest management": ["income"],
};

export function parseFamilyFromMessage(text: string, families: string[]): string | null {
  const t = text.trim();
  const lower = t.toLowerCase();
  if (CHALLENGE_PREFIX.test(t)) {
    const rest = t.replace(CHALLENGE_PREFIX, "").replace(/\.\s*$/, "").trim();
    const hit = families.find((f) => f.toLowerCase() === rest.toLowerCase());
    if (hit) return hit;
  }
  const exact = families.find((f) => lower.includes(f.toLowerCase()));
  if (exact) return exact;
  for (const hint of FAMILY_HINTS) {
    if (hint.re.test(t) && families.includes(hint.family)) return hint.family;
  }
  return null;
}

export function parseIndicatorFromMessage(
  text: string,
  indicators: IndicatorMeta[]
): string | null {
  const t = text.trim();
  const lower = normMatch(t);
  if (OBJECTIVE_PREFIX.test(t)) {
    const rest = normMatch(t.replace(OBJECTIVE_PREFIX, "").replace(/\.\s*$/, ""));
    const hit = indicators.find((i) => normMatch(i.label) === rest);
    if (hit) return hit.key;
  }
  const keys = new Set(indicators.map((i) => i.key));
  for (const ind of indicators) {
    if (normMatch(ind.label) === lower || normMatch(ind.key) === lower) return ind.key;
  }
  let best: { key: string; score: number } | null = null;
  for (const { phrase, key } of INDICATOR_PHRASES) {
    if (!keys.has(key)) continue;
    const p = normMatch(phrase);
    if (p && lower.includes(p)) {
      const score = p.length;
      if (!best || score > best.score) best = { key, score };
    }
  }
  if (best) return best.key;
  for (const ind of indicators) {
    if (lower.includes(normMatch(ind.key))) return ind.key;
    const labelCore = normMatch(
      ind.label.replace(/^increase |^improve |^reduce /i, "")
    );
    if (labelCore.length > 4 && lower.includes(labelCore)) return ind.key;
  }
  return null;
}

export function messageHasLocation(text: string): boolean {
  return COORD_RE.test(text) || PLACE_HINT_RE.test(text);
}

export function deriveChatSetup(
  turns: { role: string; content: string }[],
  lastQuery: RecommendQuery | null,
  mapLat: number | null,
  mapLon: number | null,
  meta: Metadata | null,
  serverSlots?: ChatSlotsPayload | null
): ChatSetupState {
  const families = meta?.practice_families ?? [];
  const indicators = meta?.indicators ?? [];

  let family =
    serverSlots?.practice_family ?? lastQuery?.practice_family ?? null;
  let indicatorKey = serverSlots?.indicator ?? lastQuery?.indicator ?? null;
  let hasLocation =
    lastQuery != null ||
    mapLat != null ||
    mapLon != null ||
    (serverSlots?.lat != null && serverSlots?.lon != null);
  const placeName = serverSlots?.place_name ?? null;

  for (const t of [...turns].reverse()) {
    if (t.role !== "user") continue;
    const f = parseFamilyFromMessage(t.content, families);
    if (f) {
      family = family ?? f;
      break;
    }
  }
  for (const t of [...turns].reverse()) {
    if (t.role !== "user") continue;
    const ind = parseIndicatorFromMessage(t.content, indicators);
    if (ind) {
      indicatorKey = indicatorKey ?? ind;
      break;
    }
  }
  for (const t of turns) {
    if (t.role !== "user") continue;
    if (messageHasLocation(t.content)) hasLocation = true;
  }

  // Prefer latest user-turn parses over stale server slots when user picks chips.
  for (const t of [...turns].reverse()) {
    if (t.role !== "user") continue;
    const f = parseFamilyFromMessage(t.content, families);
    if (f && /^my challenge is\s+/i.test(t.content.trim())) {
      family = f;
      break;
    }
  }
  for (const t of [...turns].reverse()) {
    if (t.role !== "user") continue;
    const ind = parseIndicatorFromMessage(t.content, indicators);
    if (ind && /^my objective is to\s+/i.test(t.content.trim())) {
      indicatorKey = ind;
      break;
    }
  }

  if (lastQuery) {
    return {
      stage: "complete",
      family: lastQuery.practice_family,
      indicatorKey: lastQuery.indicator,
      hasLocation: true,
      placeName,
    };
  }

  let stage: ChatSetupStage = "challenge";
  if (family && !indicatorKey) stage = "objective";
  else if (family && indicatorKey && !hasLocation) stage = "location";
  else if (family && indicatorKey && hasLocation) stage = "complete";

  return { stage, family, indicatorKey, hasLocation, placeName };
}

export function indicatorsForFamily(meta: Metadata, family: string): IndicatorMeta[] {
  const byFam = meta.indicators_by_family?.[family];
  const exclude = new Set(QUICK_REPLY_EXCLUDE[family] ?? []);
  const keys = (byFam?.length ? byFam : meta.indicators.map((i) => i.key)).filter(
    (k) => !exclude.has(k)
  );
  const map = new Map(meta.indicators.map((i) => [i.key, i]));
  return keys.map((k) => map.get(k)).filter(Boolean) as IndicatorMeta[];
}

/** Context-aware label so livestock goals don't read as "crop yield". */
export function indicatorLabelForFamily(family: string | null, ind: IndicatorMeta): string {
  if (!family) return ind.label;
  if (family === "Livestock production and management") {
    if (ind.key === "biomass yield") return "Increase fodder & forage biomass";
  }
  if (family === "Erosion control and water management") {
    if (ind.key === "yield") return "Increase yield while protecting soil";
  }
  if (family === "Agro-forestry and forest management") {
    if (ind.key === "yield") return "Increase crop & tree productivity";
  }
  return ind.label;
}

export function shortFamilyName(family: string): string {
  return family.replace(/\s+and management$/i, "");
}

export function deriveDashboardSetup(
  lat: number | null,
  lon: number | null,
  family: string,
  indicator: string,
  reopenChallenge: boolean
): {
  stage: DashboardSetupStage;
  hasLocation: boolean;
} {
  const hasLocation = lat != null && lon != null;
  if (!hasLocation) return { stage: "location", hasLocation };
  if (reopenChallenge || !family) return { stage: "challenge", hasLocation };
  if (!indicator) return { stage: "objective", hasLocation };
  return { stage: "complete", hasLocation };
}

export function sanitizeIndicatorForFamily(
  meta: Metadata,
  family: string,
  indicatorKey: string
): string {
  if (!indicatorKey || !family) return "";
  const allowed = indicatorsForFamily(meta, family).map((i) => i.key);
  return allowed.includes(indicatorKey) ? indicatorKey : "";
}
