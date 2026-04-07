import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Map, { Source, Layer, Popup, NavigationControl } from "react-map-gl/mapbox";
import type { MapRef, MapMouseEvent } from "react-map-gl/mapbox";
import type { GeoJSON as GeoJSONType } from "geojson";
import "mapbox-gl/dist/mapbox-gl.css";

import { Text, Badge, Button } from "@radix-ui/themes";
import { FunnelSimple } from "@phosphor-icons/react";
import { fetchApi } from "../api/client";
import { formatCurrency, formatDate, formatStreet } from "../lib/utils";
import { getRadixHex, propertyTypeColor, propertyTypeLabel, propertyTypeMatchExpression, categoryColor } from "../lib/theme";
import MultiSelectDropdown from "../components/ui/MultiSelectDropdown";
import { RETAIL_CATEGORIES, ALL_BRANDS, BRAND_TO_CATEGORY, expandBrandFilter } from "../lib/brandCategories";

// ============================================================
// Constants
// ============================================================

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;
const MAP_STYLE = "mapbox://styles/mapbox/satellite-streets-v12";
const DEFAULT_CENTER = { longitude: -79.5, latitude: 44.3 };
const DEFAULT_ZOOM = 6;
const PARCEL_ZOOM_THRESHOLD = 12;

const EMPTY_FC: GeoJSONType = { type: "FeatureCollection", features: [] };

const PROPERTY_TYPES = [
  "retail", "industrial", "multifamily", "office", "farm",
  "res-land", "comm-ind-land", "hotel-motel", "restaurant-bar",
  "other-bldg", "other-land",
];

// Dropdown options for category and brand multi-selects
const CATEGORY_OPTIONS = RETAIL_CATEGORIES.map((cat) => ({
  value: cat,
  label: cat,
  color: categoryColor(cat),
}));

const BRAND_OPTIONS = ALL_BRANDS.map((brand) => ({
  value: brand,
  label: brand,
  group: BRAND_TO_CATEGORY[brand],
  color: categoryColor(BRAND_TO_CATEGORY[brand]),
}));

// ============================================================
// Mapbox layer paint/layout definitions
// ============================================================

// ============================================================
// Component
// ============================================================

interface PropertyFeature {
  id: string;
  address: string;
  city: string;
  owner: string | null;
  latest_price: number | null;
  latest_date: string | null;
  transaction_count: number;
}

interface PopupData {
  id: string;
  display_address: string;
  city: string;
  current_owner_name: string | null;
  most_recent_sale_price: number | null;
  most_recent_sale_date: string | null;
  transaction_count: number;
  primary_property_type: string | null;
  acreage: number | null;
  photo_url: string | null;
  photo_count: number;
  tenants: { brand: string; category: string }[];
  assessed_value?: number | null;
  zoning?: string | null;
  property_description?: string | null;
}

interface PopupInfo {
  longitude: number;
  latitude: number;
  properties: PropertyFeature;
  detail?: PopupData | null;
  loading?: boolean;
}

// Mapbox queryRenderedFeatures stringifies nulls to "null" and arrays to strings
function cleanProp(val: any): string {
  if (val === null || val === undefined || val === "null" || val === "undefined") return "";
  return String(val);
}
function cleanNum(val: any): number | null {
  if (val === null || val === undefined || val === "null") return null;
  const n = Number(val);
  return isNaN(n) ? null : n;
}

type SortOption = "latest_date" | "price_high" | "price_low" | "most_txns";

export default function MapPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const mapRef = useRef<MapRef>(null);

  // Restore viewport from URL search params (for browser back button)
  const initialViewState = useMemo(() => {
    const lat = parseFloat(searchParams.get("lat") || "");
    const lng = parseFloat(searchParams.get("lng") || "");
    const z = parseFloat(searchParams.get("z") || "");
    if (!isNaN(lat) && !isNaN(lng) && !isNaN(z)) {
      return { latitude: lat, longitude: lng, zoom: z };
    }
    return { ...DEFAULT_CENTER, zoom: DEFAULT_ZOOM };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only read on mount

  // Data
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [geoData, setGeoData] = useState<any>(EMPTY_FC);
  const [parcelData, setParcelData] = useState<any>(EMPTY_FC);
  const [selectedParcel, setSelectedParcel] = useState<any>(EMPTY_FC);
  const [loading, setLoading] = useState(true);
  const [categoryFilters, setCategoryFilters] = useState<Set<string>>(new Set());
  const [brandFilters, setBrandFilters] = useState<Set<string>>(new Set());

  // UI state
  const [popupInfo, setPopupInfo] = useState<PopupInfo | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortOption>("latest_date");
  const [showFilters, setShowFilters] = useState(false);

  // Filters
  const [cityFilter, setCityFilter] = useState<string>("");
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set());
  const [minPrice, setMinPrice] = useState<string>("");
  const [maxPrice, setMaxPrice] = useState<string>("");
  const [cities, setCities] = useState<string[]>([]);

  // Viewport tracking for property list
  const [viewportBounds, setViewportBounds] = useState<{ south: number; north: number; west: number; east: number } | null>(null);
  const [currentZoom, setCurrentZoom] = useState(DEFAULT_ZOOM);
  const parcelFetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ============================================================
  // Data loading
  // ============================================================

  useEffect(() => {
    fetchApi<any>("/geo/properties").then((data) => {
      setGeoData(data);
      setLoading(false);
    });
    fetchApi<any>("/properties/filters").then((data) => {
      setCities(data.cities || []);
    });
  }, []);

  // Fetch parcels when zoomed in
  const fetchParcels = useCallback((bounds: { south: number; north: number; west: number; east: number }) => {
    if (parcelFetchTimer.current) clearTimeout(parcelFetchTimer.current);
    parcelFetchTimer.current = setTimeout(() => {
      fetchApi<any>("/geo/parcels", {
        south: String(bounds.south),
        north: String(bounds.north),
        west: String(bounds.west),
        east: String(bounds.east),
      }).then(setParcelData);
    }, 300);
  }, []);

  // ============================================================
  // Map event handlers
  // ============================================================

  const onMoveEnd = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const bounds = map.getBounds();
    if (!bounds) return;
    const zoom = map.getZoom();
    const center = map.getCenter();
    setCurrentZoom(zoom);

    // Persist viewport to URL so browser back button restores position
    const params = new URLSearchParams(window.location.search);
    params.set("lat", center.lat.toFixed(5));
    params.set("lng", center.lng.toFixed(5));
    params.set("z", zoom.toFixed(1));
    window.history.replaceState(null, "", `${window.location.pathname}?${params}`);

    const b = {
      south: bounds.getSouth(),
      north: bounds.getNorth(),
      west: bounds.getWest(),
      east: bounds.getEast(),
    };
    setViewportBounds(b);

    if (zoom >= PARCEL_ZOOM_THRESHOLD) {
      fetchParcels(b);
    } else {
      setParcelData(EMPTY_FC);
    }
  }, [fetchParcels]);

  // When map loads (including restored viewport), fetch parcels if zoomed in
  const onMapLoad = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const bounds = map.getBounds();
    if (!bounds) return;
    const zoom = map.getZoom();
    setCurrentZoom(zoom);

    const b = {
      south: bounds.getSouth(),
      north: bounds.getNorth(),
      west: bounds.getWest(),
      east: bounds.getEast(),
    };
    setViewportBounds(b);

    if (zoom >= PARCEL_ZOOM_THRESHOLD) {
      fetchParcels(b);
    }
  }, [fetchParcels]);

  const onMapClick = useCallback((e: MapMouseEvent) => {
    const map = mapRef.current?.getMap();
    if (!map) return;

    // Check clusters first
    const clusterFeatures = map.queryRenderedFeatures(e.point, { layers: ["clusters"] });
    if (clusterFeatures.length > 0) {
      const feature = clusterFeatures[0];
      const clusterId = feature.properties?.cluster_id;
      const source = map.getSource("properties") as any;
      source.getClusterExpansionZoom(clusterId, (err: any, zoom: number) => {
        if (err) return;
        map.easeTo({
          center: (feature.geometry as any).coordinates,
          zoom: zoom + 1,
          duration: 500,
        });
      });
      return;
    }

    // Check unclustered points
    const pointFeatures = map.queryRenderedFeatures(e.point, { layers: ["unclustered-point"] });
    if (pointFeatures.length > 0) {
      const feature = pointFeatures[0];
      const coords = (feature.geometry as any).coordinates;
      const props = feature.properties as any;

      map.easeTo({ center: coords, zoom: Math.max(map.getZoom(), 15), duration: 500 });

      setSelectedId(props.id);
      setPopupInfo({
        longitude: coords[0],
        latitude: coords[1],
        properties: {
          id: props.id,
          address: cleanProp(props.address),
          city: cleanProp(props.city),
          owner: cleanProp(props.owner) || null,
          latest_price: cleanNum(props.latest_price),
          latest_date: cleanProp(props.latest_date) || null,
          transaction_count: cleanNum(props.transaction_count) ?? 0,
        },
        loading: true,
      });
      fetchPopupDetail(props.id);
      return;
    }

    // Check parcel polygons
    const parcelFeatures = map.queryRenderedFeatures(e.point, { layers: ["parcel-fill"] });
    if (parcelFeatures.length > 0) {
      const feature = parcelFeatures[0];
      const props = feature.properties as any;

      setSelectedParcel({
        type: "FeatureCollection",
        features: [feature as any],
      });
      setSelectedId(props.id);

      setPopupInfo({
        longitude: props.lng || e.lngLat.lng,
        latitude: props.lat || e.lngLat.lat,
        properties: {
          id: props.id,
          address: cleanProp(props.address),
          city: cleanProp(props.city),
          owner: cleanProp(props.owner) || null,
          latest_price: cleanNum(props.latest_price),
          latest_date: cleanProp(props.latest_date) || null,
          transaction_count: cleanNum(props.transaction_count) ?? 0,
        },
        loading: true,
      });
      fetchPopupDetail(props.id);
      return;
    }

    // Clicked empty space — clear selection
    setPopupInfo(null);
    setSelectedId(null);
    setSelectedParcel(EMPTY_FC);
  }, []);

  const onMapMouseEnter = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) map.getCanvas().style.cursor = "pointer";
  }, []);

  const onMapMouseLeave = useCallback(() => {
    const map = mapRef.current?.getMap();
    if (map) map.getCanvas().style.cursor = "";
  }, []);

  // ============================================================
  // Filtered map data — applies to BOTH map layers AND list panel
  // ============================================================

  // Expand category selections into a combined brand set for filtering
  const activeBrands = useMemo(
    () => expandBrandFilter(categoryFilters, brandFilters),
    [categoryFilters, brandFilters],
  );

  const hasBrandFilter = activeBrands.size > 0;

  /** Check if a feature matches the active brand/category filter */
  const featureMatchesBrands = useCallback((f: any): boolean => {
    if (!hasBrandFilter) return true;
    const brands: string[] = f.properties.tenant_brands
      ? (typeof f.properties.tenant_brands === "string" ? JSON.parse(f.properties.tenant_brands) : f.properties.tenant_brands)
      : [];
    return brands.some((b: string) => activeBrands.has(b));
  }, [hasBrandFilter, activeBrands]);

  /**
   * Hard filters (city, type, price) remove features entirely.
   * Brand/category is a soft filter — it stamps `_matched` on each
   * feature so the map can dim non-matching ones instead of hiding them.
   */
  const filterFeatures = useCallback((features: any[]) => {
    let filtered = features;
    // Hard filters — these remove features
    if (cityFilter) {
      filtered = filtered.filter((f: any) => f.properties.city === cityFilter);
    }
    if (typeFilters.size > 0) {
      filtered = filtered.filter((f: any) => typeFilters.has(f.properties.primary_property_type));
    }
    if (minPrice) {
      const min = parseInt(minPrice);
      if (!isNaN(min)) filtered = filtered.filter((f: any) => (f.properties.latest_price ?? 0) >= min);
    }
    if (maxPrice) {
      const max = parseInt(maxPrice);
      if (!isNaN(max)) filtered = filtered.filter((f: any) => (f.properties.latest_price ?? 0) <= max);
    }
    // Soft filter — stamp _matched flag for brand/category dimming
    if (hasBrandFilter) {
      filtered = filtered.map((f: any) => ({
        ...f,
        properties: {
          ...f.properties,
          _matched: featureMatchesBrands(f) ? 1 : 0,
        },
      }));
    } else {
      // No brand filter — all matched
      filtered = filtered.map((f: any) => ({
        ...f,
        properties: { ...f.properties, _matched: 1 },
      }));
    }
    return filtered;
  }, [cityFilter, typeFilters, minPrice, maxPrice, hasBrandFilter, featureMatchesBrands]);

  // Filtered GeoJSON for the map points source
  const filteredGeoData = useMemo(() => {
    if (!geoData || geoData.type !== "FeatureCollection") return EMPTY_FC;
    const features = filterFeatures(geoData.features || []);
    return { type: "FeatureCollection" as const, features };
  }, [geoData, filterFeatures]);

  // Filtered parcel polygons for the parcels source
  const filteredParcelData = useMemo(() => {
    if (!parcelData || parcelData.type !== "FeatureCollection") return EMPTY_FC;
    const features = filterFeatures(parcelData.features || []);
    return { type: "FeatureCollection" as const, features };
  }, [parcelData, filterFeatures]);

  // Visible properties for the list panel (filtered + viewport-bounded + sorted)
  const visibleProperties = useMemo(() => {
    let features = (filteredGeoData as any).features || [];

    // Filter to viewport
    if (viewportBounds) {
      features = features.filter((f: any) => {
        const [lng, lat] = f.geometry.coordinates;
        return lat >= viewportBounds.south && lat <= viewportBounds.north &&
               lng >= viewportBounds.west && lng <= viewportBounds.east;
      });
    }

    // Sort: matched items first when brand filter is active, then by sort option
    const sorted = [...features];
    sorted.sort((a: any, b: any) => {
      // Matched items float to top when brand filter active
      if (hasBrandFilter) {
        const aMatch = a.properties._matched ?? 1;
        const bMatch = b.properties._matched ?? 1;
        if (aMatch !== bMatch) return bMatch - aMatch;
      }
      switch (sortBy) {
        case "latest_date":
          return (b.properties.latest_date || "").localeCompare(a.properties.latest_date || "");
        case "price_high":
          return (b.properties.latest_price ?? 0) - (a.properties.latest_price ?? 0);
        case "price_low":
          return (a.properties.latest_price ?? 0) - (b.properties.latest_price ?? 0);
        case "most_txns":
          return (b.properties.transaction_count ?? 0) - (a.properties.transaction_count ?? 0);
        default:
          return 0;
      }
    });

    return sorted.slice(0, 200); // Cap at 200 for perf
  }, [filteredGeoData, viewportBounds, sortBy, hasBrandFilter]);

  // ============================================================
  // Popup detail fetching
  // ============================================================

  const fetchPopupDetail = useCallback((propertyId: string) => {
    setPopupInfo((prev) => prev ? { ...prev, loading: true, detail: null } : prev);
    fetchApi<PopupData>(`/properties/${propertyId}/popup`).then((data) => {
      setPopupInfo((prev) => prev ? { ...prev, detail: data, loading: false } : prev);
    }).catch(() => {
      setPopupInfo((prev) => prev ? { ...prev, loading: false } : prev);
    });
  }, []);

  // ============================================================
  // Filter bar helpers
  // ============================================================

  const activeFilterCount = [
    cityFilter ? 1 : 0,
    typeFilters.size > 0 ? 1 : 0,
    minPrice ? 1 : 0,
    maxPrice ? 1 : 0,
    categoryFilters.size > 0 ? 1 : 0,
    brandFilters.size > 0 ? 1 : 0,
  ].reduce((a, b) => a + b, 0);

  const clearFilters = () => {
    setCityFilter("");
    setTypeFilters(new Set());
    setMinPrice("");
    setMaxPrice("");
    setCategoryFilters(new Set());
    setBrandFilters(new Set());
  };

  const toggleType = (t: string) => {
    setTypeFilters((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  // ============================================================
  // Property list card click
  // ============================================================

  const flyToProperty = (feature: any) => {
    const [lng, lat] = feature.geometry.coordinates;
    const map = mapRef.current?.getMap();
    if (map) {
      map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 15), duration: 800 });
    }
    setSelectedId(feature.properties.id);
    setPopupInfo({
      longitude: lng,
      latitude: lat,
      properties: feature.properties,
      loading: true,
    });
    fetchPopupDetail(feature.properties.id);
  };

  // ============================================================
  // Render
  // ============================================================

  return (
    <div className="page-full-bleed relative" style={{ display: "flex", height: "100%" }}>
      {/* Map */}
      <div style={{ flex: 1, position: "relative" }}>
        {/* Filter bar */}
        <div
          className="absolute top-0 left-0 right-0 z-10 flex items-center gap-2 px-3 border-b"
          style={{
            height: "var(--map-filter-height)",
            background: "rgba(255,255,255,0.95)",
            backdropFilter: "blur(8px)",
            borderColor: "var(--gray-4)",
          }}
        >
          <Button
            size="1"
            variant={showFilters ? "solid" : "soft"}
            onClick={() => setShowFilters(!showFilters)}
          >
            <FunnelSimple size={14} />
            Filters
            {activeFilterCount > 0 && (
              <Badge size="1" color="jade" variant="solid" className="ml-1">{activeFilterCount}</Badge>
            )}
          </Button>

          {showFilters && (
            <>
              {/* City */}
              <select
                value={cityFilter}
                onChange={(e) => setCityFilter(e.target.value)}
                className="h-7 px-1.5 text-[13px] rounded border border-[var(--gray-6)] bg-white"
                style={{ minWidth: 120 }}
              >
                <option value="">All Cities</option>
                {cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>

              {/* Price range */}
              <input
                type="number"
                placeholder="Min $"
                value={minPrice}
                onChange={(e) => setMinPrice(e.target.value)}
                className="h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
                style={{ width: 90 }}
              />
              <span className="text-[12px]" style={{ color: "var(--gray-9)" }}>to</span>
              <input
                type="number"
                placeholder="Max $"
                value={maxPrice}
                onChange={(e) => setMaxPrice(e.target.value)}
                className="h-7 px-2 text-[13px] rounded border border-[var(--gray-6)] bg-white"
                style={{ width: 90 }}
              />

              {activeFilterCount > 0 && (
                <Button size="1" variant="ghost" onClick={clearFilters}>Clear</Button>
              )}
            </>
          )}

          <div className="ml-auto text-[12px]" style={{ color: "var(--gray-9)" }}>
            {loading ? "Loading..." : `${((filteredGeoData as any).features?.length ?? 0).toLocaleString()} properties`}
          </div>
        </div>

        {/* Property type badges (when filter expanded) */}
        {showFilters && (
          <div
            className="absolute left-0 right-0 z-10 flex flex-wrap gap-1.5 px-3 py-2 border-b"
            style={{
              top: "var(--map-filter-height)",
              background: "rgba(255,255,255,0.95)",
              backdropFilter: "blur(8px)",
              borderColor: "var(--gray-4)",
            }}
          >
            {PROPERTY_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => toggleType(t)}
                className="px-2 py-0.5 rounded text-[12px] border transition-colors"
                style={{
                  background: typeFilters.has(t) ? getRadixHex(propertyTypeColor(t), 4) : "transparent",
                  borderColor: typeFilters.has(t) ? getRadixHex(propertyTypeColor(t), 7) : "var(--gray-6)",
                  color: typeFilters.has(t) ? getRadixHex(propertyTypeColor(t), 11) : "var(--gray-11)",
                  fontWeight: typeFilters.has(t) ? 500 : 400,
                }}
              >
                {propertyTypeLabel(t)}
              </button>
            ))}
            <span className="text-[11px] mx-1" style={{ color: "var(--gray-8)" }}>|</span>
            <MultiSelectDropdown
              placeholder="Categories"
              options={CATEGORY_OPTIONS}
              selected={categoryFilters}
              onChange={setCategoryFilters}
            />
            <MultiSelectDropdown
              placeholder="Brands"
              options={BRAND_OPTIONS}
              selected={brandFilters}
              onChange={setBrandFilters}
              searchable
              grouped
              maxHeight={360}
            />
          </div>
        )}

        <Map
          ref={mapRef}
          mapboxAccessToken={MAPBOX_TOKEN}
          initialViewState={initialViewState}
          style={{ width: "100%", height: "100%" }}
          mapStyle={MAP_STYLE}
          onClick={onMapClick}
          onMoveEnd={onMoveEnd}
          onLoad={onMapLoad}
          interactiveLayerIds={["clusters", "unclustered-point", "parcel-fill"]}
          onMouseEnter={onMapMouseEnter}
          onMouseLeave={onMapMouseLeave}
        >
          <NavigationControl position="bottom-right" />

          {/* Properties source — clustered */}
          <Source
            id="properties"
            type="geojson"
            data={filteredGeoData}
            cluster={true}
            clusterRadius={50}
            clusterMaxZoom={PARCEL_ZOOM_THRESHOLD}
          >
            {/* Cluster circles */}
            <Layer
              id="clusters"
              type="circle"
              filter={["has", "point_count"]}
              paint={{
                "circle-color": getRadixHex("jade", 9),
                "circle-radius": [
                  "step", ["get", "point_count"],
                  18, 10, 22, 50, 26, 200, 30, 1000, 36,
                ],
                "circle-stroke-width": 2,
                "circle-stroke-color": "#ffffff",
                "circle-opacity": 0.85,
              }}
            />
            {/* Cluster count label */}
            <Layer
              id="cluster-count"
              type="symbol"
              filter={["has", "point_count"]}
              layout={{
                "text-field": ["get", "point_count_abbreviated"],
                "text-size": 13,
                "text-font": ["DIN Pro Medium", "Arial Unicode MS Bold"],
              }}
              paint={{ "text-color": "#ffffff" }}
            />
            {/* Individual points — colored by property type, dimmed when unmatched */}
            <Layer
              id="unclustered-point"
              type="circle"
              filter={["!", ["has", "point_count"]]}
              paint={{
                "circle-color": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  getRadixHex("gray", 7),
                  propertyTypeMatchExpression(9),
                ] as any,
                "circle-radius": 7,
                "circle-stroke-width": 2,
                "circle-stroke-color": "#ffffff",
                "circle-opacity": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  0.4,
                  0.9,
                ] as any,
              }}
            />
          </Source>

          {/* Parcel polygons — loaded at zoom >= 14, dimmed when unmatched */}
          <Source id="parcels" type="geojson" data={filteredParcelData}>
            <Layer
              id="parcel-fill"
              type="fill"
              paint={{
                "fill-color": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  getRadixHex("gray", 5),
                  propertyTypeMatchExpression(9),
                ] as any,
                "fill-opacity": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  0.12,
                  0.22,
                ] as any,
              }}
            />
            <Layer
              id="parcel-outline"
              type="line"
              paint={{
                "line-color": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  getRadixHex("gray", 7),
                  propertyTypeMatchExpression(11),
                ] as any,
                "line-width": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  1,
                  2,
                ] as any,
                "line-opacity": [
                  "case",
                  ["==", ["get", "_matched"], 0],
                  0.5,
                  1,
                ] as any,
              }}
            />
          </Source>

          {/* Selected parcel highlight */}
          <Source id="selected-parcel" type="geojson" data={selectedParcel}>
            <Layer
              id="selected-parcel-fill"
              type="fill"
              paint={{
                "fill-color": getRadixHex("amber", 9),
                "fill-opacity": 0.3,
              }}
            />
            <Layer
              id="selected-parcel-outline"
              type="line"
              paint={{
                "line-color": getRadixHex("amber", 11),
                "line-width": 2.5,
                "line-opacity": 1,
              }}
            />
          </Source>

          {/* Popup */}
          {popupInfo && (
            <Popup
              longitude={popupInfo.longitude}
              latitude={popupInfo.latitude}
              closeOnClick={false}
              onClose={() => { setPopupInfo(null); setSelectedId(null); setSelectedParcel(EMPTY_FC); }}
              maxWidth="340px"
              anchor="bottom"
              offset={12}
            >
              <div style={{ minWidth: 280 }}>
                {/* Photo */}
                {popupInfo.detail?.photo_url && (
                  <div className="relative" style={{ height: 140, overflow: "hidden" }}>
                    <img
                      src={popupInfo.detail.photo_url}
                      alt=""
                      className="w-full h-full object-cover"
                      style={{ display: "block" }}
                    />
                    {(popupInfo.detail.photo_count ?? 0) > 1 && (
                      <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded text-[11px] font-medium"
                           style={{ background: "rgba(0,0,0,0.6)", color: "#fff" }}>
                        1 of {popupInfo.detail.photo_count}
                      </div>
                    )}
                  </div>
                )}

                <div className="p-4">
                  {/* Price + Type badge */}
                  {popupInfo.detail ? (
                    <>
                      <div className="flex items-center gap-2">
                        {popupInfo.detail.most_recent_sale_price && (
                          <Text size="4" weight="bold">{formatCurrency(popupInfo.detail.most_recent_sale_price)}</Text>
                        )}
                        {popupInfo.detail.primary_property_type && (
                          <Badge size="1" variant="soft" color={propertyTypeColor(popupInfo.detail.primary_property_type) as any}>
                            {propertyTypeLabel(popupInfo.detail.primary_property_type)}
                          </Badge>
                        )}
                      </div>

                      {/* Address */}
                      <Text size="2" weight="medium" className="block mt-1">
                        {formatStreet(popupInfo.detail.display_address) || "No address"}
                      </Text>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {[popupInfo.detail.city, popupInfo.detail.zoning].filter(Boolean).join(" | ")}
                      </Text>

                      {/* Owner */}
                      {popupInfo.detail.current_owner_name && (
                        <Text size="1" className="block mt-2" style={{ color: "var(--gray-11)" }}>
                          {popupInfo.detail.current_owner_name}
                        </Text>
                      )}

                      {/* Stats row */}
                      <div className="flex items-center gap-4 mt-2 text-[12px]" style={{ color: "var(--gray-9)" }}>
                        {popupInfo.detail.most_recent_sale_date && (
                          <span>{formatDate(popupInfo.detail.most_recent_sale_date)}</span>
                        )}
                        {popupInfo.detail.acreage && (
                          <span>{popupInfo.detail.acreage} acres</span>
                        )}
                        {popupInfo.detail.assessed_value && (
                          <span>Assessed: {formatCurrency(popupInfo.detail.assessed_value)}</span>
                        )}
                      </div>

                      {/* Tenant badges */}
                      {popupInfo.detail.tenants.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {popupInfo.detail.tenants.slice(0, 4).map((t) => (
                            <Badge key={t.brand} size="1" variant="outline" color={categoryColor(t.category) as any}>
                              {t.brand}
                            </Badge>
                          ))}
                          {popupInfo.detail.tenants.length > 4 && (
                            <Badge size="1" variant="outline" color="gray">+{popupInfo.detail.tenants.length - 4}</Badge>
                          )}
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="flex gap-2 mt-3">
                        <Button
                          size="1"
                          variant="solid"
                          className="flex-1"
                          onClick={() => navigate(`/properties/${popupInfo.detail!.id}`, { state: { from: "map" } })}
                        >
                          View Property
                        </Button>
                      </div>
                    </>
                  ) : popupInfo.loading ? (
                    <Text size="2" style={{ color: "var(--gray-9)" }}>Loading...</Text>
                  ) : (
                    <>
                      <Text size="3" weight="medium" className="block">
                        {formatStreet(popupInfo.properties.address) || "No address"}
                      </Text>
                      {popupInfo.properties.city && (
                        <Text size="2" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>{popupInfo.properties.city}</Text>
                      )}
                      <Button
                        size="1"
                        variant="soft"
                        className="mt-3 w-full"
                        onClick={() => navigate(`/properties/${popupInfo.properties.id}`, { state: { from: "map" } })}
                      >
                        View Property
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </Popup>
          )}
        </Map>
      </div>

      {/* Property list panel */}
      <div
        className="flex flex-col border-l"
        style={{
          width: "var(--map-list-width)",
          background: "var(--gray-1)",
          borderColor: "var(--gray-4)",
        }}
      >
        {/* Panel header */}
        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--gray-4)" }}>
          <Text size="2" weight="medium">{visibleProperties.length.toLocaleString()} properties</Text>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="h-7 px-1.5 text-[12px] rounded border bg-white"
            style={{ borderColor: "var(--gray-6)" }}
          >
            <option value="latest_date">Latest Sale</option>
            <option value="price_high">Price: High → Low</option>
            <option value="price_low">Price: Low → High</option>
            <option value="most_txns">Most Transactions</option>
          </select>
        </div>

        {/* Scrollable card list */}
        <div className="flex-1 overflow-y-auto">
          {visibleProperties.length === 0 ? (
            <div className="flex items-center justify-center h-32">
              <Text size="2" style={{ color: "var(--gray-9)" }}>
                {loading ? "Loading properties..." : currentZoom < 8 ? "Zoom in to see properties" : "No properties in view"}
              </Text>
            </div>
          ) : (
            <div className="flex flex-col">
              {visibleProperties.map((f: any) => {
                const p = f.properties;
                const isSelected = p.id === selectedId;
                const isDimmed = hasBrandFilter && !p._matched;
                return (
                  <div
                    key={p.id}
                    className="px-4 py-3 border-b cursor-pointer transition-colors"
                    style={{
                      borderColor: "var(--gray-4)",
                      background: isSelected ? "var(--amber-2)" : "transparent",
                      opacity: isDimmed ? 0.45 : 1,
                    }}
                    onClick={() => flyToProperty(f)}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = isSelected ? "var(--amber-2)" : "var(--gray-2)";
                      if (isDimmed) e.currentTarget.style.opacity = "0.7";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = isSelected ? "var(--amber-2)" : "transparent";
                      if (isDimmed) e.currentTarget.style.opacity = "0.45";
                    }}
                  >
                    <Text size="2" weight="medium" className="block">
                      {formatStreet(p.address)}
                    </Text>
                    <Text size="1" className="block mt-0.5" style={{ color: "var(--gray-9)" }}>
                      {p.city}
                    </Text>
                    <div className="flex items-center justify-between mt-1.5">
                      <Text size="2" weight="medium" style={{ color: "var(--gray-12)" }}>
                        {formatCurrency(p.latest_price)}
                      </Text>
                      <Text size="1" style={{ color: "var(--gray-9)" }}>
                        {formatDate(p.latest_date)}
                      </Text>
                    </div>
                    {p.transaction_count > 1 && (
                      <Text size="1" className="mt-1 block" style={{ color: "var(--gray-9)" }}>
                        {p.transaction_count} transactions
                      </Text>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
