import { useEffect, useState } from "react";
import { fetchContext } from "@/lib/api";
import type { Bounds } from "@/lib/types";

export function inBounds(lat: number, lon: number, b: Bounds): boolean {
  return lat >= b.lat[0] && lat <= b.lat[1] && lon >= b.lon[0] && lon <= b.lon[1];
}

/**
 * Resolve the agro-ecological belt under a pin (debounced, abortable).
 * "Loading" is DERIVED from whether the stored answer matches the current pin,
 * so no state is set synchronously inside the effect (F-1).
 */
export function useZone(lat: number | null, lon: number | null, bounds: Bounds | null) {
  const valid = lat != null && lon != null && bounds != null && inBounds(lat, lon, bounds);
  const key = valid ? `${lat},${lon}` : null;
  const [zone, setZone] = useState<{ key: string; belt: string | null } | null>(null);

  useEffect(() => {
    if (!key || lat == null || lon == null) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      fetchContext(lat, lon, ctl.signal)
        .then((c) => setZone({ key, belt: c.aez_belt }))
        .catch(() => {
          if (!ctl.signal.aborted) setZone({ key, belt: null });
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [key, lat, lon]);

  const resolved = key != null && zone?.key === key;
  return {
    valid,
    belt: resolved ? zone!.belt : null,
    loading: key != null && !resolved,
  };
}
