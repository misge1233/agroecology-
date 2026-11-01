"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { fetchNearestPlace, type NearestPlace } from "@/lib/api";

const CACHE = new Map<string, NearestPlace>();
/** Within this distance the pin is "in" the town; beyond it, "near" it. */
const IN_TOWN_KM = 5;

/**
 * "Debre Birhan (9.68, 39.53)" or "Near Debre Birhan (9.62, 39.60)" for a pin
 * (U9, D10); plain coordinates while loading, offline, or far from any town.
 */
export function usePlaceLabel(lat: number | null | undefined, lon: number | null | undefined): string | null {
  const t = useTranslations("advisor.results.context");
  const format = useFormatter();
  const key = lat != null && lon != null ? `${lat.toFixed(3)},${lon.toFixed(3)}` : null;
  const [place, setPlace] = useState<{ key: string; hit: NearestPlace } | null>(null);

  useEffect(() => {
    if (!key || lat == null || lon == null) return;
    if (CACHE.has(key)) return;
    const ctl = new AbortController();
    fetchNearestPlace(lat, lon, ctl.signal)
      .then((hit) => {
        CACHE.set(key, hit);
        setPlace({ key, hit });
      })
      .catch(() => undefined);
    return () => ctl.abort();
  }, [key, lat, lon]);

  if (lat == null || lon == null) return null;
  const c = (n: number) => format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const hit = (key ? CACHE.get(key) : undefined) ?? (place?.key === key ? place.hit : null);
  if (!hit?.found || !hit.name) return `${c(lat)}, ${c(lon)}`;
  const near = (hit.distance_km ?? 0) > IN_TOWN_KM;
  return t(near ? "placeNear" : "placeExact", { name: hit.name, lat: c(lat), lon: c(lon) });
}
