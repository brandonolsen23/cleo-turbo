/**
 * Satellite map for PropertyDetailPage — shows a zoomed-in satellite view
 * centered on the property with the parcel boundary outlined.
 *
 * Lazy-loaded to avoid blocking the page if mapbox-gl has issues.
 */

import Map, { Source, Layer, NavigationControl } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

interface Props {
  lat: number;
  lng: number;
  parcelFC: GeoJSON.FeatureCollection | null;
  parcelColor: string;
  parcelOutlineColor: string;
  token: string;
  mapStyle: string;
}

export default function PropertySatelliteMap({
  lat,
  lng,
  parcelFC,
  parcelColor,
  parcelOutlineColor,
  token,
  mapStyle,
}: Props) {
  return (
    <Map
      initialViewState={{
        longitude: lng,
        latitude: lat,
        zoom: parcelFC ? 16.5 : 15,
      }}
      style={{ width: "100%", height: 340 }}
      mapStyle={mapStyle}
      mapboxAccessToken={token}
      interactive={true}
      scrollZoom={true}
      dragPan={true}
      dragRotate={false}
      doubleClickZoom={true}
      attributionControl={false}
    >
      <NavigationControl position="top-right" showCompass={false} />

      {/* Parcel boundary polygon */}
      {parcelFC && (
        <Source id="detail-parcel" type="geojson" data={parcelFC}>
          <Layer
            id="detail-parcel-fill"
            type="fill"
            paint={{
              "fill-color": parcelColor,
              "fill-opacity": 0.2,
            }}
          />
          <Layer
            id="detail-parcel-outline"
            type="line"
            paint={{
              "line-color": parcelOutlineColor,
              "line-width": 2.5,
            }}
          />
        </Source>
      )}
    </Map>
  );
}
