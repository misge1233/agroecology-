"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import {
  MapContainer,
  Marker,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";

// A self-contained SVG pin (avoids Leaflet's default icon asset issues in bundlers).
const pinIcon = L.divIcon({
  className: "agro-pin",
  html: `<svg width="30" height="40" viewBox="0 0 30 40" xmlns="http://www.w3.org/2000/svg">
    <path d="M15 0C6.7 0 0 6.7 0 15c0 10.5 15 25 15 25s15-14.5 15-25C30 6.7 23.3 0 15 0z"
      fill="#4F46E5" stroke="#ffffff" stroke-width="2"/>
    <circle cx="15" cy="15" r="5.5" fill="#ffffff"/>
  </svg>`,
  iconSize: [30, 40],
  iconAnchor: [15, 40],
});

const ETHIOPIA_CENTER: [number, number] = [9.15, 40.5];

function ClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(
        Number(e.latlng.lat.toFixed(4)),
        Number(e.latlng.lng.toFixed(4))
      );
    },
  });
  return null;
}

function Recenter({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lon], Math.max(map.getZoom(), 8), { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lat, lon]);
  return null;
}

export default function LocationMap({
  lat,
  lon,
  onPick,
}: {
  lat: number | null;
  lon: number | null;
  onPick: (lat: number, lon: number) => void;
}) {
  const hasPoint = lat != null && lon != null;
  const center: [number, number] = hasPoint
    ? [lat as number, lon as number]
    : ETHIOPIA_CENTER;

  return (
    <MapContainer
      center={center}
      zoom={hasPoint ? 8 : 6}
      scrollWheelZoom
      className="h-full w-full"
      style={{ background: "var(--panel)" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ClickHandler onPick={onPick} />
      {hasPoint && (
        <>
          <Marker
            position={[lat as number, lon as number]}
            draggable
            icon={pinIcon}
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
