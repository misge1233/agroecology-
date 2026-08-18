"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { MapPin, Loader2, AlertTriangle, Navigation } from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchContext } from "@/lib/api";
import type { Bounds } from "@/lib/types";

const LocationMap = dynamic(() => import("./location-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-panel text-sm text-mute">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading map…
    </div>
  ),
});

function inBounds(lat: number, lon: number, b: Bounds): boolean {
  return (
    lat >= b.lat[0] && lat <= b.lat[1] && lon >= b.lon[0] && lon <= b.lon[1]
  );
}

export function LocationPicker({
  lat,
  lon,
  onChange,
  bounds,
  mapClassName,
}: {
  lat: number | null;
  lon: number | null;
  onChange: (lat: number | null, lon: number | null) => void;
  bounds: Bounds;
  /** e.g. h-72 lg:h-[22rem] for a taller dashboard map */
  mapClassName?: string;
}) {
  const [latStr, setLatStr] = useState(lat != null ? String(lat) : "");
  const [lonStr, setLonStr] = useState(lon != null ? String(lon) : "");
  const [zone, setZone] = useState<string | null>(null);
  const [zoneLoading, setZoneLoading] = useState(false);
  const [gpsOn, setGpsOn] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const gpsWatchRef = useRef<number | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  function disableGps() {
    setGpsOn(false);
    setGpsError(null);
  }

  // Keep the numeric fields in sync when the point changes from the map.
  useEffect(() => {
    setLatStr(lat != null ? String(lat) : "");
  }, [lat]);
  useEffect(() => {
    setLonStr(lon != null ? String(lon) : "");
  }, [lon]);

  const parsedLat = latStr.trim() === "" ? null : Number(latStr);
  const parsedLon = lonStr.trim() === "" ? null : Number(lonStr);
  const hasBoth = parsedLat != null && parsedLon != null &&
    !Number.isNaN(parsedLat) && !Number.isNaN(parsedLon);
  const valid = hasBoth && inBounds(parsedLat as number, parsedLon as number, bounds);
  const outOfRange = hasBoth && !valid;

  // Resolve the agro-ecological zone (debounced) whenever a valid point is set.
  useEffect(() => {
    if (lat == null || lon == null || !inBounds(lat, lon, bounds)) {
      setZone(null);
      return;
    }
    setZoneLoading(true);
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    const t = setTimeout(() => {
      fetchContext(lat, lon, ctl.signal)
        .then((c) => setZone(c.aez_belt))
        .catch(() => setZone(null))
        .finally(() => setZoneLoading(false));
    }, 350);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [lat, lon, bounds]);

  useEffect(() => {
    if (!gpsOn) {
      if (gpsWatchRef.current != null && navigator.geolocation) {
        navigator.geolocation.clearWatch(gpsWatchRef.current);
        gpsWatchRef.current = null;
      }
      setGpsLoading(false);
      return;
    }

    if (!navigator.geolocation) {
      setGpsError("Geolocation is not available in this browser.");
      setGpsOn(false);
      return;
    }

    setGpsLoading(true);
    setGpsError(null);

    gpsWatchRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setGpsLoading(false);
        const la = Number(pos.coords.latitude.toFixed(4));
        const lo = Number(pos.coords.longitude.toFixed(4));
        if (!inBounds(la, lo, bounds)) {
          setGpsError(
            "Your GPS fix is outside Ethiopia. Turn off GPS and pick a point on the map."
          );
          return;
        }
        setGpsError(null);
        onChangeRef.current(la, lo);
      },
      () => {
        setGpsLoading(false);
        setGpsError("Could not read GPS. Check permissions or turn GPS off and use the map.");
      },
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 20_000 }
    );

    return () => {
      if (gpsWatchRef.current != null) {
        navigator.geolocation.clearWatch(gpsWatchRef.current);
        gpsWatchRef.current = null;
      }
    };
  }, [gpsOn, bounds]);

  function commitField(nextLat: string, nextLon: string) {
    const nl = nextLat.trim() === "" ? null : Number(nextLat);
    const no = nextLon.trim() === "" ? null : Number(nextLon);
    if (
      nl != null && no != null &&
      !Number.isNaN(nl) && !Number.isNaN(no) &&
      inBounds(nl, no, bounds)
    ) {
      onChange(Number(nl.toFixed(4)), Number(no.toFixed(4)));
    } else if (nextLat.trim() === "" || nextLon.trim() === "") {
      onChange(null, null);
    }
  }

  return (
    <div className="space-y-3">
      <div
        className={
          mapClassName ??
          "h-60 overflow-hidden rounded-2xl border border-edge shadow-soft sm:h-64"
        }
      >
        <LocationMap
          lat={lat}
          lon={lon}
          onPick={(la, lo) => {
            disableGps();
            onChange(la, lo);
          }}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm">
          <span className="mb-1.5 block text-[13px] font-medium text-ink">
            Latitude
          </span>
          <input
            inputMode="decimal"
            value={latStr}
            placeholder={`${bounds.lat[0]}–${bounds.lat[1]}`}
            onChange={(e) => {
              disableGps();
              setLatStr(e.target.value);
              commitField(e.target.value, lonStr);
            }}
            aria-invalid={outOfRange}
            className="w-full rounded-2xl border border-edge bg-canvas/60 px-3.5 py-2.5 text-sm outline-none transition focus:border-ink/20 focus:ring-4 focus:ring-ink/5"
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1.5 block text-[13px] font-medium text-ink">
            Longitude
          </span>
          <input
            inputMode="decimal"
            value={lonStr}
            placeholder={`${bounds.lon[0]}–${bounds.lon[1]}`}
            onChange={(e) => {
              disableGps();
              setLonStr(e.target.value);
              commitField(latStr, e.target.value);
            }}
            aria-invalid={outOfRange}
            className="w-full rounded-2xl border border-edge bg-canvas/60 px-3.5 py-2.5 text-sm outline-none transition focus:border-ink/20 focus:ring-4 focus:ring-ink/5"
          />
        </label>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1">
          {gpsError ? (
            <p className="flex items-center gap-1.5 text-[12px] text-soil" role="alert">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              {gpsError}
            </p>
          ) : outOfRange ? (
            <p className="flex items-center gap-1.5 text-[12px] text-soil" role="alert">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Point is outside Ethiopia (lat {bounds.lat[0]}–{bounds.lat[1]}, lon{" "}
              {bounds.lon[0]}–{bounds.lon[1]}). Move the pin inside the country.
            </p>
          ) : valid ? (
            <p className="flex items-center gap-1.5 text-[12px] text-mute">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-leaf" />
              {gpsOn ? (
                <span>
                  GPS on —{" "}
                  {zoneLoading ? (
                    <span className="inline-flex items-center gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" /> resolving zone…
                    </span>
                  ) : zone ? (
                    <>
                      zone{" "}
                      <span className="font-medium text-ink">{zone}</span>
                    </>
                  ) : (
                    "location synced from your device"
                  )}
                </span>
              ) : zoneLoading ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" /> resolving zone…
                </span>
              ) : zone ? (
                <>
                  Agro-ecological zone:{" "}
                  <span className="font-medium text-ink">{zone}</span>
                </>
              ) : (
                <span>Zone not available for this point.</span>
              )}
            </p>
          ) : (
            <p className="flex items-center gap-1.5 text-[12px] text-mute">
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              {gpsOn && gpsLoading
                ? "Waiting for GPS fix…"
                : "Click the map or type coordinates to drop a pin."}
            </p>
          )}
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={gpsOn}
          aria-label="Use GPS for farm location"
          onClick={() => setGpsOn((v) => !v)}
          className={cn(
            "inline-flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-[13px] font-semibold transition focus-ring",
            gpsOn
              ? "border-transparent bg-leaf text-white shadow-soft"
              : "border-edge bg-elevated/80 text-ink hover:border-ink/15"
          )}
        >
          {gpsLoading && gpsOn ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Navigation className="h-4 w-4" aria-hidden />
          )}
          Use GPS
          <span
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide",
              gpsOn ? "bg-white/25 text-white" : "bg-panel text-mute"
            )}
          >
            {gpsOn ? "On" : "Off"}
          </span>
        </button>
      </div>
    </div>
  );
}
