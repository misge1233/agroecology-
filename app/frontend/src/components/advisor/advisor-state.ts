import { sanitizeIndicatorForFamily } from "@/lib/chat-flow";
import type { Metadata } from "@/lib/types";
import { inBounds } from "./use-zone";

export type StepKey = "location" | "challenge" | "objective" | "crop" | "results";
export const STEP_ORDER: StepKey[] = ["location", "challenge", "objective", "crop", "results"];
export const TOP_N_OPTIONS = [1, 2, 3, 5] as const;

/** The request, exactly as carried by the URL (`?lat&lon&family&indicator&crop&top`). */
export interface AdvisorParams {
  lat: number | null;
  lon: number | null;
  family: string | null;
  indicator: string | null;
  crop: string | null;
  topN: number;
}

function num(raw: string | null): number | null {
  if (raw == null || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** Parse + validate the URL against /metadata (unknown values are dropped). */
export function parseParams(sp: URLSearchParams, meta: Metadata | null): AdvisorParams {
  let lat = num(sp.get("lat"));
  let lon = num(sp.get("lon"));
  if (lat != null && lon != null && meta && !inBounds(lat, lon, meta.bounds)) {
    lat = null;
    lon = null;
  }
  if (lat == null || lon == null) {
    lat = null;
    lon = null;
  }
  let family = sp.get("family")?.trim() || null;
  if (family && meta && !meta.practice_families.includes(family)) family = null;
  let indicator = sp.get("indicator")?.trim() || null;
  if (indicator && meta && family) indicator = sanitizeIndicatorForFamily(meta, family, indicator) || null;
  if (!family) indicator = null;
  let crop = sp.get("crop")?.trim() || null;
  if (crop && meta && !meta.crop_types.includes(crop)) crop = null;
  const top = Number(sp.get("top"));
  const topN = (TOP_N_OPTIONS as readonly number[]).includes(top) ? top : 1;
  return { lat, lon, family, indicator, crop, topN };
}

export function toSearch(p: AdvisorParams): string {
  const qs = new URLSearchParams();
  if (p.lat != null && p.lon != null) {
    qs.set("lat", String(p.lat));
    qs.set("lon", String(p.lon));
  }
  if (p.family) qs.set("family", p.family);
  if (p.indicator) qs.set("indicator", p.indicator);
  if (p.crop) qs.set("crop", p.crop);
  if (p.topN !== 1) qs.set("top", String(p.topN));
  return qs.toString();
}

/** The first step still missing, or results when the request is complete. */
export function autoStep(p: AdvisorParams): StepKey {
  if (p.lat == null || p.lon == null) return "location";
  if (!p.family) return "challenge";
  if (!p.indicator) return "objective";
  return "results";
}

export function isComplete(p: AdvisorParams): boolean {
  return p.lat != null && p.lon != null && !!p.family && !!p.indicator;
}

/** Stable cache key for one scoring request. */
export function requestKey(p: AdvisorParams): string | null {
  if (!isComplete(p)) return null;
  return [p.lat, p.lon, p.family, p.indicator, p.crop ?? "", p.topN].join("|");
}
