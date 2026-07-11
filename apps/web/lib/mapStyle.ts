/**
 * Basemap style constants (spec §4 "Basemap"). OpenFreeMap dark is primary
 * (free for any use, no key); CARTO Dark Matter is the runtime fallback if
 * the OpenFreeMap style fails to load.
 */

export const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/dark";

export const FALLBACK_STYLE_URL =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

/** Required OpenFreeMap basemap attribution. */
export const OPENFREEMAP_ATTRIBUTION = "OpenFreeMap © OpenMapTiles, Data from OpenStreetMap";

/** Attribution for the CARTO Dark Matter fallback style. */
export const CARTO_ATTRIBUTION = "© OpenStreetMap contributors © CARTO";
