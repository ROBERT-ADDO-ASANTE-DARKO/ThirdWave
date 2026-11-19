import { TileLayer } from "react-leaflet";
import "./MapStyle.css";

// Shared by every Leaflet map in this app (Live Incident Map, Road
// Closures, ...) -- mirrors streamlit_app/map_tiles.py's
// Streets/Satellite/Dark/Terrain picker exactly: same Mapbox style IDs,
// same MAPBOX_API_KEY (here exposed to the client bundle via
// vite.config.ts's `define`, since Mapbox tokens are meant for client
// use, unlike the officer key -- see that file's comment). Degrades to
// Streets-only, same as the Streamlit picker, when no token is
// configured.

export const MAP_STYLES = ["Streets", "Satellite", "Dark", "Terrain"] as const;
export type MapStyle = (typeof MAP_STYLES)[number];

const MAPBOX_STYLE_ID: Record<Exclude<MapStyle, "Streets">, string> = {
  Satellite: "satellite-streets-v12",
  Dark: "dark-v11",
  Terrain: "outdoors-v12",
};

export function hasMapboxToken(): boolean {
  return Boolean(import.meta.env.VITE_MAPBOX_TOKEN);
}

export function StyleTileLayer({ style }: { style: MapStyle }) {
  if (style === "Streets" || !hasMapboxToken()) {
    return (
      <TileLayer
        key="streets"
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
    );
  }
  return (
    <TileLayer
      key={style}
      url={`https://api.mapbox.com/styles/v1/mapbox/${MAPBOX_STYLE_ID[style]}/tiles/256/{z}/{x}/{y}@2x?access_token=${import.meta.env.VITE_MAPBOX_TOKEN}`}
      attribution="&copy; Mapbox"
    />
  );
}

export function MapStylePicker({ value, onChange }: { value: MapStyle; onChange: (style: MapStyle) => void }) {
  const tokenPresent = hasMapboxToken();
  return (
    <div className="map-style-picker">
      {MAP_STYLES.map((style) => (
        <button
          key={style}
          type="button"
          className={`map-style-btn ${value === style ? "is-active" : ""}`}
          onClick={() => onChange(style)}
          disabled={style !== "Streets" && !tokenPresent}
          title={style !== "Streets" && !tokenPresent ? "No Mapbox token configured" : undefined}
        >
          {style}
        </button>
      ))}
    </div>
  );
}
