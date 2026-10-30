"use client";

import { useEffect, useId, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import { preconnect } from "react-dom";
import dynamic from "next/dynamic";
import { Loader2, LocateFixed, Map as MapIcon, MapPin, Search } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { fetchGeocode } from "@/lib/api";
import type { Bounds, GeocodeResponse } from "@/lib/types";
import { aezName } from "@/i18n/glossary";
import type { Locale } from "@/i18n/routing";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { inBounds } from "./use-zone";

// Phone detection as an external store (F-1). The server snapshot is `null`
// ("unknown") so the first client render — hydration — mounts no map at all;
// desktops mount it right after, phones wait for a tap (U2 0d: the first map
// tile was the LCP element of step 1).
const PHONE_QUERY = "(max-width: 767px)";
function subscribePhone(onChange: () => void) {
  const mq = window.matchMedia(PHONE_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}
const getPhone = () => window.matchMedia(PHONE_QUERY).matches;
const getPhoneServer = (): boolean | null => null;
function useIsPhone(): boolean | null {
  return useSyncExternalStore(subscribePhone, getPhone, getPhoneServer);
}

function MapLoading() {
  const t = useTranslations("advisor.location");
  return (
    <div className="flex h-full w-full items-center justify-center bg-surface-2 text-sm text-muted">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> {t("mapLoading")}
    </div>
  );
}

const LocationMap = dynamic(() => import("@/components/location-map"), {
  ssr: false,
  loading: MapLoading,
});

function round4(n: number) {
  return Number(n.toFixed(4));
}

/**
 * Latitude/longitude fields. Mounted with a `key` of the external point so a
 * map click resets them (derived state via key, F-1) while typing never
 * fights the parent: values commit on blur or Enter, only when both are
 * valid and inside Ethiopia.
 */
function CoordinateFields({
  initialLat,
  initialLon,
  bounds,
  onCommit,
}: {
  initialLat: number | null;
  initialLon: number | null;
  bounds: Bounds;
  onCommit: (lat: number | null, lon: number | null) => void;
}) {
  const t = useTranslations("advisor.location");
  const id = useId();
  const [latStr, setLatStr] = useState(initialLat != null ? String(initialLat) : "");
  const [lonStr, setLonStr] = useState(initialLon != null ? String(initialLon) : "");
  const la = latStr.trim() === "" ? null : Number(latStr);
  const lo = lonStr.trim() === "" ? null : Number(lonStr);
  const both = la != null && lo != null && Number.isFinite(la) && Number.isFinite(lo);
  const outside = both && !inBounds(la as number, lo as number, bounds);
  const valid = both && !outside;

  function commit() {
    if (valid) {
      const nl = round4(la as number);
      const no = round4(lo as number);
      if (nl !== initialLat || no !== initialLon) onCommit(nl, no);
    } else if (latStr.trim() === "" && lonStr.trim() === "" && initialLat != null) {
      onCommit(null, null);
    }
  }
  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor={`${id}-lat`}>{t("latitude")}</Label>
          <Input
            id={`${id}-lat`}
            inputMode="decimal"
            autoComplete="off"
            value={latStr}
            onChange={(e) => setLatStr(e.target.value)}
            onBlur={commit}
            onKeyDown={onKey}
            aria-invalid={outside || undefined}
            aria-describedby={`${id}-hint${outside ? ` ${id}-err` : ""}`}
            className="tabular"
          />
        </div>
        <div>
          <Label htmlFor={`${id}-lon`}>{t("longitude")}</Label>
          <Input
            id={`${id}-lon`}
            inputMode="decimal"
            autoComplete="off"
            value={lonStr}
            onChange={(e) => setLonStr(e.target.value)}
            onBlur={commit}
            onKeyDown={onKey}
            aria-invalid={outside || undefined}
            aria-describedby={`${id}-hint${outside ? ` ${id}-err` : ""}`}
            className="tabular"
          />
        </div>
      </div>
      <p id={`${id}-hint`} className="mt-1.5 text-xs text-muted">
        {t("coordinateHint")}
      </p>
      {outside ? (
        <p id={`${id}-err`} role="alert" className="mt-1.5 text-sm text-danger-text">
          {t("outside", {
            latMin: String(bounds.lat[0]),
            latMax: String(bounds.lat[1]),
            lonMin: String(bounds.lon[0]),
            lonMax: String(bounds.lon[1]),
          })}
        </p>
      ) : null}
    </div>
  );
}

/** Offline gazetteer search. "Searching" is derived from query vs. answer (F-1). */
function PlaceSearch({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  const t = useTranslations("advisor.location");
  const format = useFormatter();
  const id = useId();
  const [query, setQuery] = useState("");
  const q = query.trim();
  const active = q.length >= 2;
  const [answer, setAnswer] = useState<{ q: string; result: GeocodeResponse | null } | null>(null);

  useEffect(() => {
    if (q.length < 2) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      fetchGeocode(q, ctl.signal)
        .then((result) => setAnswer({ q, result }))
        .catch(() => {
          if (!ctl.signal.aborted) setAnswer({ q, result: null });
        });
    }, 300);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [q]);

  const resolved = active && answer?.q === q;
  const hit = resolved && answer?.result?.found ? answer.result : null;
  const fmt = (n: number) => format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div>
      <Label htmlFor={id}>{t("search")}</Label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
        <Input
          id={id}
          type="search"
          autoComplete="off"
          value={query}
          placeholder={t("searchPlaceholder")}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
          aria-describedby={`${id}-status`}
        />
      </div>
      <div id={`${id}-status`} aria-live="polite" className="mt-2 min-h-5 text-sm">
        {active && !resolved ? (
          <span className="inline-flex items-center gap-2 text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> {t("searching")}
          </span>
        ) : hit && hit.lat != null && hit.lon != null ? (
          <button
            type="button"
            onClick={() => {
              onPick(hit.lat as number, hit.lon as number);
              setQuery("");
            }}
            className="inline-flex items-center gap-2 rounded-control border border-border bg-surface px-3 py-1.5 text-sm hover:border-primary/50 hover:bg-surface-2"
          >
            <MapPin className="h-4 w-4 text-primary" aria-hidden />
            <span className="font-medium">{hit.name}</span>
            <span className="tabular text-muted">
              {fmt(hit.lat as number)}, {fmt(hit.lon as number)}
            </span>
          </button>
        ) : resolved ? (
          <span className="text-muted">{t("searchNone")}</span>
        ) : null}
      </div>
    </div>
  );
}

export interface LocationPickerProps {
  lat: number | null;
  lon: number | null;
  bounds: Bounds;
  onChange: (lat: number | null, lon: number | null) => void;
  zone: { belt: string | null; loading: boolean };
  mapClassName?: string;
  /** Mount the map immediately regardless of viewport (the chat sheet is opened on purpose). */
  eagerMap?: boolean;
}

/** Map + coordinates + place search + device location. Shared by Advisor and Chat. */
export function LocationPicker({ lat, lon, bounds, onChange, zone, mapClassName, eagerMap = false }: LocationPickerProps) {
  const t = useTranslations("advisor.location");
  const ta = useTranslations("a11y");
  const locale = useLocale() as Locale;
  const format = useFormatter();
  const isPhone = useIsPhone();
  const [mapRequested, setMapRequested] = useState(false);
  const [tiles, setTiles] = useState<"unknown" | "ok" | "failed">("unknown");
  const [gps, setGps] = useState<{ status: "idle" | "locating" | "error"; message?: string }>({ status: "idle" });
  const hasPoint = lat != null && lon != null;
  // Desktop: as soon as the viewport is known. Phone: on request, or when a pin exists.
  const showMap = eagerMap || mapRequested || isPhone === false || (isPhone === true && hasPoint);
  // The map's tiles are the LCP element of step 1: open the connections only when it will mount.
  if (showMap) for (const host of ["a", "b", "c"]) preconnect(`https://${host}.tile.openstreetmap.org`);
  const fmt = (n: number) => format.number(n, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const pinLabel = hasPoint ? t("pinAt", { lat: fmt(lat as number), lon: fmt(lon as number) }) : t("noPin");

  function useMyLocation() {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGps({ status: "error", message: t("gpsUnavailable") });
      return;
    }
    setGps({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const la = round4(pos.coords.latitude);
        const lo = round4(pos.coords.longitude);
        if (!inBounds(la, lo, bounds)) {
          setGps({ status: "error", message: t("gpsOutside") });
          return;
        }
        setGps({ status: "idle" });
        onChange(la, lo);
      },
      () => setGps({ status: "error", message: t("gpsFailed") }),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 30_000 }
    );
  }

  return (
    <div className="space-y-4">
      <div
        role="region"
        aria-label={t("mapLabel")}
        className={mapClassName ?? "h-56 overflow-hidden rounded-card border border-border sm:h-80"}
      >
        {showMap ? (
          <LocationMap lat={lat} lon={lon} onPick={(la, lo) => onChange(la, lo)} pinLabel={pinLabel} onTiles={setTiles} />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 bg-surface-2 px-6 text-center">
            <MapIcon className="h-8 w-8 text-muted" aria-hidden />
            {isPhone ? (
              <>
                <p className="max-w-xs text-sm text-muted">{t("mapDeferred")}</p>
                <Button type="button" variant="outline" size="sm" onClick={() => setMapRequested(true)}>
                  <MapPin className="h-4 w-4" aria-hidden />
                  {t("showMap")}
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted">{t("mapLoading")}</p>
            )}
          </div>
        )}
      </div>
      {tiles === "failed" ? (
        <Alert variant="warning" title={t("tilesFailed")} />
      ) : null}
      <p className="sr-only">{ta("pinSetByKeyboard")}</p>

      <div className="grid gap-4 md:grid-cols-2">
        <PlaceSearch onPick={(la, lo) => onChange(la, lo)} />
        <CoordinateFields
          key={`${lat ?? ""}|${lon ?? ""}`}
          initialLat={lat}
          initialLon={lon}
          bounds={bounds}
          onCommit={onChange}
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="inline-flex min-w-0 items-center gap-2 text-sm text-muted" aria-live="polite">
          <MapPin className={hasPoint ? "h-4 w-4 shrink-0 text-primary" : "h-4 w-4 shrink-0"} aria-hidden />
          {!hasPoint ? (
            <span>{t("noPin")}</span>
          ) : zone.loading ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> {t("zoneLoading")}
            </span>
          ) : zone.belt ? (
            <span>
              {t("zone")}: <span className="font-medium text-text">{aezName(zone.belt, locale)}</span>
            </span>
          ) : (
            <span>{t("zoneUnavailable")}</span>
          )}
        </p>
        <div className="flex shrink-0 flex-col items-start gap-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={useMyLocation}
            loading={gps.status === "locating"}
          >
            {gps.status !== "locating" ? <LocateFixed className="h-4 w-4" aria-hidden /> : null}
            {gps.status === "locating" ? t("locating") : t("useMyLocation")}
          </Button>
          {gps.status === "error" ? (
            <p role="alert" className="text-sm text-danger-text">
              {gps.message}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Advisor step 1: the picker plus the step heading and the Next button. */
export function LocationStep(props: LocationPickerProps & { onNext: () => void }) {
  const t = useTranslations("advisor.location");
  const tc = useTranslations("common");
  const ready = props.lat != null && props.lon != null;
  return (
    <div className="space-y-5">
      <div>
        <h2 id="advisor-step-title" className="text-xl sm:text-2xl">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("help")}</p>
      </div>
      <LocationPicker {...props} />
      <div className="flex justify-end">
        <Button type="button" size="lg" disabled={!ready} onClick={props.onNext}>
          {tc("next")}
        </Button>
      </div>
    </div>
  );
}
