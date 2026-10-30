"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import type { Bounds } from "@/lib/types";

// A self-contained SVG pin in the primary token (avoids Leaflet's default
// icon asset issues in bundlers; follows the theme because it is inline SVG).
const pinIcon = L.divIcon({
  className: "agro-pin",
  html: `<svg width="30" height="40" viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z"
      fill="var(--primary)" stroke="var(--surface)" stroke-width="2"/>
    <circle cx="15" cy="15" r="5.5" fill="var(--surface)"/>
  </svg>`,
  iconSize: [30, 40],
  iconAnchor: [15, 40],
});

const ETHIOPIA_CENTER: [number, number] = [9.15, 40.5];

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
  const frame: L.LatLngBoundsExpression | undefined =
    !hasPoint && bounds ? [[bounds.lat[0], bounds.lon[0]], [bounds.lat[1], bounds.lon[1]]] : undefined;
  const tileStats = useRef({ ok: 0, failed: 0 });

  return (
    <MapContainer
      {...(frame ? { bounds: frame, boundsOptions: { padding: [12, 12] as [number, number] } } : { center, zoom: hasPoint ? 8 : 6 })}
      scrollWheelZoom
      // Quarter-step zoom so the country fits the panel snugly instead of snapping out a whole level.
      zoomSnap={0.25}
      className="h-full w-full"
      style={{ background: "var(--surface-2)" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
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
