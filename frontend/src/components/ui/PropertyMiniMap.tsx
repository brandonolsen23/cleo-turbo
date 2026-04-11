import { useState, useEffect, useRef, useCallback } from "react";
import Map, { Marker, Popup, NavigationControl } from "react-map-gl/mapbox";
import type { MapRef } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";
import { Text } from "@radix-ui/themes";
import { Star } from "@phosphor-icons/react";
import { getRadixHex, assetClassColor } from "../../lib/theme";
import { assetClassLabel, formatCurrency } from "../../lib/utils";
import type { MiniMapProperty } from "../../types";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const MAP_STYLE = "mapbox://styles/mapbox/light-v11";

// ── Types ──────────────────────────────────────────────────────

interface PropertyMiniMapProps {
  /** Properties to show as pins */
  properties: MiniMapProperty[];
  /** Optional HQ marker (for groups) */
  hq?: { lat: number; lng: number; label?: string } | null;
  /** Height of the map container */
  height?: number;
  /** Click handler — navigate to property detail */
  onPropertyClick?: (propertyId: string) => void;
}

interface PopupData {
  property: MiniMapProperty;
  lng: number;
  lat: number;
}

// ── Pin color from asset class ────────────────────────────────

function pinColor(assetClass: string | null): string {
  if (!assetClass) return getRadixHex("gray", 9);
  return getRadixHex(assetClassColor(assetClass), 9);
}

// ── Dot marker (small circle) ──────────────────────────────────

function DotMarker({
  color,
  size = 12,
  onClick,
}: {
  color: string;
  size?: number;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        backgroundColor: color,
        border: "2px solid white",
        boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        cursor: onClick ? "pointer" : "default",
      }}
    />
  );
}

// ── HQ marker (star) ─────────────────────────────────────────

function HqMarker() {
  return (
    <div
      style={{
        width: 28,
        height: 28,
        borderRadius: "50%",
        backgroundColor: getRadixHex("gray", 12),
        border: "2px solid white",
        boxShadow: "0 1px 4px rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Star size={14} weight="fill" color="white" />
    </div>
  );
}

// ── Legend ──────────────────────────────────────────────────────

function Legend({ assetClasses }: { assetClasses: string[] }) {
  if (assetClasses.length === 0) return null;

  return (
    <div
      className="absolute bottom-2 left-2 rounded-md px-2.5 py-1.5 flex flex-wrap gap-x-3 gap-y-1"
      style={{
        backgroundColor: "rgba(255, 255, 255, 0.9)",
        backdropFilter: "blur(4px)",
        fontSize: 11,
        color: "var(--gray-11)",
        zIndex: 5,
        maxWidth: "calc(100% - 16px)",
      }}
    >
      {assetClasses.map((ac) => (
        <span key={ac} className="inline-flex items-center gap-1 whitespace-nowrap">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: pinColor(ac) }}
          />
          {assetClassLabel(ac)}
        </span>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────

export default function PropertyMiniMap({
  properties,
  hq,
  height = 320,
  onPropertyClick,
}: PropertyMiniMapProps) {
  const mapRef = useRef<MapRef>(null);
  const [popup, setPopup] = useState<PopupData | null>(null);
  const [loaded, setLoaded] = useState(false);

  // Unique asset classes present (for legend)
  const assetClasses = [
    ...new Set(properties.map((p) => p.asset_class).filter(Boolean) as string[]),
  ].sort();

  // Fit bounds when properties change
  const fitBounds = useCallback(() => {
    const map = mapRef.current;
    if (!map || properties.length === 0) return;

    const lngs = properties.map((p) => p.lng);
    const lats = properties.map((p) => p.lat);

    // Include HQ in bounds if present
    if (hq) {
      lngs.push(hq.lng);
      lats.push(hq.lat);
    }

    const minLng = Math.min(...lngs);
    const maxLng = Math.max(...lngs);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);

    // Single point — just center on it
    if (minLng === maxLng && minLat === maxLat) {
      map.flyTo({ center: [minLng, minLat], zoom: 13, duration: 800 });
      return;
    }

    map.fitBounds(
      [
        [minLng, minLat],
        [maxLng, maxLat],
      ],
      { padding: 50, duration: 800, maxZoom: 14 },
    );
  }, [properties, hq]);

  useEffect(() => {
    if (loaded) fitBounds();
  }, [loaded, fitBounds]);

  if (!MAPBOX_TOKEN) {
    return (
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] flex items-center justify-center"
        style={{ height }}
      >
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          Map unavailable (no Mapbox token)
        </Text>
      </div>
    );
  }

  if (properties.length === 0) {
    return (
      <div
        className="rounded-[var(--card-radius)] border border-[var(--gray-6)] flex items-center justify-center"
        style={{ height }}
      >
        <Text size="2" style={{ color: "var(--gray-9)" }}>
          No mappable properties
        </Text>
      </div>
    );
  }

  return (
    <div
      className="rounded-[var(--card-radius)] border border-[var(--gray-6)] overflow-hidden relative"
      style={{ height }}
    >
      <Map
        ref={mapRef}
        mapboxAccessToken={MAPBOX_TOKEN}
        mapStyle={MAP_STYLE}
        initialViewState={{
          longitude: properties[0]?.lng ?? -79.5,
          latitude: properties[0]?.lat ?? 44.3,
          zoom: 6,
        }}
        onLoad={() => setLoaded(true)}
        reuseMaps
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="top-right" showCompass={false} />

        {/* Property pins */}
        {properties.map((p) => (
          <Marker key={p.id} longitude={p.lng} latitude={p.lat} anchor="center">
            <DotMarker
              color={pinColor(p.asset_class)}
              onClick={() =>
                setPopup({ property: p, lng: p.lng, lat: p.lat })
              }
            />
          </Marker>
        ))}

        {/* HQ marker */}
        {hq && (
          <Marker longitude={hq.lng} latitude={hq.lat} anchor="center">
            <HqMarker />
          </Marker>
        )}

        {/* Popup */}
        {popup && (
          <Popup
            longitude={popup.lng}
            latitude={popup.lat}
            anchor="bottom"
            offset={10}
            closeOnClick={false}
            onClose={() => setPopup(null)}
            maxWidth="240px"
          >
            <div
              className="flex flex-col gap-0.5 text-[12px]"
              style={{ cursor: onPropertyClick ? "pointer" : "default" }}
              onClick={() => {
                if (onPropertyClick) onPropertyClick(popup.property.id);
              }}
            >
              <span className="font-medium" style={{ color: "var(--gray-12)" }}>
                {popup.property.display_address}
              </span>
              <span style={{ color: "var(--gray-9)" }}>{popup.property.city}</span>
              {popup.property.asset_class && (
                <span style={{ color: pinColor(popup.property.asset_class) }}>
                  {assetClassLabel(popup.property.asset_class)}
                </span>
              )}
              {popup.property.most_recent_sale_price != null && (
                <span style={{ color: "var(--gray-11)" }}>
                  {formatCurrency(popup.property.most_recent_sale_price)}
                </span>
              )}
            </div>
          </Popup>
        )}
      </Map>

      {/* Legend */}
      <Legend assetClasses={assetClasses} />
    </div>
  );
}
