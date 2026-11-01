"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useRef } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { Bounds } from "@/lib/types";

// A self-contained SVG pin in the primary token (avoids Leaflet's default
// icon asset issues in bundlers; follows the theme because it is inline SVG).
const pinIcon = L.divIcon({
  className: "agro-pin",
  html: `<svg width="30" height="40" viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z"
      fill="rgb(var(--primary))" stroke="rgb(var(--surface))" stroke-width="2"/>
    <circle cx="15" cy="15" r="5.5" fill="rgb(var(--surface))"/>
  </svg>`,
  iconSize: [30, 40],
  iconAnchor: [15, 40],
});

const ETHIOPIA_CENTER: [number, number] = [9.15, 40.5];

/**
 * Tile provider (U9, D7). OpenStreetMap's public tiles are fine for
 * development and light use; production sets a keyed provider (for example
 * MapTiler or Stadia) through these two variables, without a code change.
 */
const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Frame the country once the container has its real size (D7): the map is
 * created inside a panel that is still laying out, so Leaflet's first fit can
 * land on the Red Sea. Re-measure, then fit, and again whenever the panel resizes.
 */
function FitCountry({ frame }: { frame: L.LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    const fit = () => {
      map.invalidateSize();
      map.fitBounds(frame, { padding: [12, 12], animate: false });
    };
    const id = requestAnimationFrame(fit);
    const ro = new ResizeObserver(() => fit());
    ro.observe(map.getContainer());
    return () => {
      cancelAnimationFrame(id);
      ro.disconnect();
    };
  }, [map, frame]);
  return null;
}

function ClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(Number(e.latlng.lat.toFixed(4)), Number(e.latlng.lng.toFixed(4)));
    },
  });
  return null;
}

function Recenter({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    map.setView([lat, lon], Math.max(map.getZoom(), 8), { animate: true });
  }, [map, lat, lon]);
  return null;
}

export default function LocationMap({
  lat,
  lon,
  bounds,
  onPick,
  pinLabel,
  onTiles,
}: {
  lat: number | null;
  lon: number | null;
  /** Country extent: with no pin the map opens framed on it (U5). */
  bounds?: Bounds;
  onPick: (lat: number, lon: number) => void;
  /** Accessible name for the marker, e.g. "Pin at 8.38, 39.37". */
  pinLabel: string;
  /** Tile health (U2 item 5): "failed" once tiles error without any success. */
  onTiles?: (status: "ok" | "failed") => void;
}) {
  const hasPoint = lat != null && lon != null;
  const center: [number, number] = hasPoint ? [lat as number, lon as number] : ETHIOPIA_CENTER;
  // No pin yet: fit the whole country (Leaflet picks the zoom for the panel size).
  const b0 = bounds?.lat[0], b1 = bounds?.lon[0], b2 = bounds?.lat[1], b3 = bounds?.lon[1];
  const frame = useMemo<L.LatLngBoundsExpression | undefined>(
    () => (!hasPoint && b0 != null && b1 != null && b2 != null && b3 != null ? [[b0, b1], [b2, b3]] : undefined),
    [hasPoint, b0, b1, b2, b3]
  );
  const tileStats = useRef({ ok: 0, failed: 0 });

  return (
    <MapContainer
      {...(frame ? { bounds: frame, boundsOptions: { padding: [12, 12] as [number, number] } } : { center, zoom: hasPoint ? 8 : 6 })}
      scrollWheelZoom
      // Quarter-step zoom so the country fits the panel snugly instead of snapping out a whole level.
      zoomSnap={0.25}
      // isolation: Leaflet's panes and controls (z-index 400 to 1000) stay inside the map
      // and never paint over the sticky header (D7).
      className="isolate h-full w-full"
      style={{ background: "rgb(var(--surface-2))" }}
    >
      <TileLayer
        attribution={TILE_ATTRIBUTION}
        url={TILE_URL}
        // Only the visible tiles on slow links: no off-screen buffer, load after pan/zoom settles.
        keepBuffer={0}
        updateWhenIdle
        eventHandlers={{
          tileload: () => {
            tileStats.current.ok += 1;
            if (tileStats.current.ok === 1) onTiles?.("ok");
          },
          tileerror: () => {
            tileStats.current.failed += 1;
            if (tileStats.current.ok === 0 && tileStats.current.failed >= 2) onTiles?.("failed");
          },
        }}
      />
      <ClickHandler onPick={onPick} />
      {frame ? <FitCountry frame={frame} /> : null}
      {hasPoint && (
        <>
          <Marker
            position={[lat as number, lon as number]}
            draggable
            icon={pinIcon}
            alt={pinLabel}
            title={pinLabel}
            eventHandlers={{
              dragend(e) {
                const p = (e.target as L.Marker).getLatLng();
                onPick(Number(p.lat.toFixed(4)), Number(p.lng.toFixed(4)));
              },
            }}
          />
          <Recenter lat={lat as number} lon={lon as number} />
        </>
      )}
    </MapContainer>
  );
}
