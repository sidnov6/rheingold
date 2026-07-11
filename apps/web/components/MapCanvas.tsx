"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Map, { useControl, type MapRef, type ViewState } from "react-map-gl/maplibre";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { FarmPopover } from "@/components/FarmPopover";
import {
  CARTO_ATTRIBUTION,
  FALLBACK_STYLE_URL,
  MAP_STYLE_URL,
  OPENFREEMAP_ATTRIBUTION,
} from "@/lib/mapStyle";
import { selectFiltered, useFleet } from "@/stores/fleet";
import type { FleetFarm } from "@/lib/types";

/**
 * The hero (§1 storyboard 0–6s, §11 "/"): full-viewport MapLibre basemap with
 * a single deck.gl ScatterplotLayer of ~30k turbine points rendered via
 * MapboxOverlay (react-map-gl useControl pattern, spec §4 rows 2–4).
 *
 * 60fps rules: one layer, module-level accessors (no per-frame allocations),
 * data identity changes only when filters change.
 */

// Germany overview (§ task: lon 10.3, lat 51.2, zoom 5.6)
const INITIAL_VIEW: ViewState = {
  longitude: 10.3,
  latitude: 51.2,
  zoom: 5.6,
  pitch: 0,
  bearing: 0,
  padding: { top: 0, bottom: 0, left: 0, right: 0 },
};

// Gold is DATA ONLY — these RGBA literals mirror the §3.1 tokens exactly,
// because deck.gl consumes numeric colors, not CSS variables.
const GOLD_500_80: [number, number, number, number] = [201, 162, 39, 204]; // --gold-500 @ 80%
const GOLD_300_HL: [number, number, number, number] = [240, 208, 106, 200]; // --gold-300 hover pulse

// sqrt(MW) → pixel radius, clamped 2–14 px by the layer (§11).
const RADIUS_K = 1.4;
const getPosition = (d: FleetFarm): [number, number] => [d.lon, d.lat];
const getRadius = (d: FleetFarm): number => RADIUS_K * Math.sqrt(d.mw);

const FLY_TO_MS = 800; // §3.3
const ROUTE_DELAY_MS = 250; // push mid-flight so the dossier arrives as the fly settles
const FADE_IN_MS = 1200; // §11 first-load shimmer

/** deck.gl overlay as a react-map-gl control (spec §4 integration pattern). */
function DeckGLOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

interface HoverInfo {
  farm: FleetFarm;
  x: number;
  y: number;
}

export function MapCanvas() {
  const router = useRouter();
  const mapRef = useRef<MapRef>(null);
  const reducedMotion = usePrefersReducedMotion();

  const farms = useFleet((s) => s.farms);
  const filters = useFleet((s) => s.filters);
  const setHovered = useFleet((s) => s.setHovered);
  const setSelected = useFleet((s) => s.setSelected);

  const filteredFarms = useMemo(() => selectFiltered(farms, filters), [farms, filters]);

  const [viewState, setViewState] = useState<ViewState>(INITIAL_VIEW);
  const [hover, setHover] = useState<HoverInfo | null>(null);

  // Basemap resilience: if the OpenFreeMap style fails before first load,
  // swap to the CARTO Dark Matter fallback once.
  const [styleUrl, setStyleUrl] = useState(MAP_STYLE_URL);
  const styleLoadedRef = useRef(false);
  const handleMapLoad = useCallback(() => {
    styleLoadedRef.current = true;
  }, []);
  const handleMapError = useCallback(() => {
    if (!styleLoadedRef.current) {
      setStyleUrl((current) => (current === MAP_STYLE_URL ? FALLBACK_STYLE_URL : current));
    }
  }, []);

  // First-load: points fade in over 1.2s (opacity 0 → 1 via layer transition);
  // skipped under prefers-reduced-motion (§11, §3.3).
  const [fadedIn, setFadedIn] = useState(false);
  useEffect(() => {
    if (farms.length > 0 && !fadedIn) {
      // one frame at opacity 0 so the transition has a start state
      const raf = requestAnimationFrame(() => setFadedIn(true));
      return () => cancelAnimationFrame(raf);
    }
  }, [farms.length, fadedIn]);
  const layerOpacity = reducedMotion || fadedIn ? 1 : 0;

  const handleHover = useCallback(
    (info: PickingInfo<FleetFarm>) => {
      if (info.object) {
        setHover({ farm: info.object, x: info.x, y: info.y });
        setHovered(info.object.id);
      } else {
        setHover(null);
        setHovered(null);
      }
    },
    [setHovered],
  );

  const routeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (routeTimer.current !== null) clearTimeout(routeTimer.current);
    };
  }, []);

  const handleClick = useCallback(
    (info: PickingInfo<FleetFarm>) => {
      const farm = info.object;
      if (!farm) return;
      setSelected(farm.id);
      if (reducedMotion) {
        router.push(`/farm/${farm.id}`);
        return;
      }
      // zoom read from the map ref (not viewState) so this callback — and the
      // layer that depends on it — is NOT recreated on every pan/zoom frame.
      const currentZoom = mapRef.current?.getZoom() ?? INITIAL_VIEW.zoom;
      mapRef.current?.flyTo({
        center: [farm.lon, farm.lat],
        zoom: Math.max(currentZoom, 10.5),
        duration: FLY_TO_MS,
        essential: false,
      });
      if (routeTimer.current !== null) clearTimeout(routeTimer.current);
      routeTimer.current = setTimeout(() => router.push(`/farm/${farm.id}`), ROUTE_DELAY_MS);
    },
    [reducedMotion, router, setSelected],
  );

  const layers = useMemo(
    () => [
      new ScatterplotLayer<FleetFarm>({
        id: "fleet-points",
        data: filteredFarms,
        getPosition,
        getRadius,
        getFillColor: GOLD_500_80,
        radiusUnits: "pixels",
        radiusMinPixels: 2,
        radiusMaxPixels: 14,
        stroked: false,
        pickable: true,
        autoHighlight: true,
        highlightColor: GOLD_300_HL,
        opacity: layerOpacity,
        transitions: reducedMotion ? undefined : { opacity: FADE_IN_MS },
        onHover: handleHover,
        onClick: handleClick,
        // data identity already changes with the filters; no accessor depends
        // on external state, so no further updateTriggers needed.
      }),
    ],
    [filteredFarms, layerOpacity, reducedMotion, handleHover, handleClick],
  );

  return (
    <div className="absolute inset-0" data-testid="map-canvas">
      <Map
        ref={mapRef}
        {...viewState}
        onMove={(e) => setViewState(e.viewState)}
        onLoad={handleMapLoad}
        onError={handleMapError}
        mapStyle={styleUrl}
        attributionControl
        customAttribution={
          styleUrl === MAP_STYLE_URL ? OPENFREEMAP_ATTRIBUTION : CARTO_ATTRIBUTION
        }
        style={{ width: "100%", height: "100%" }}
        cursor={hover ? "pointer" : "grab"}
        reuseMaps
      >
        <DeckGLOverlay layers={layers} />
      </Map>
      {hover && <FarmPopover farm={hover.farm} x={hover.x} y={hover.y} />}
    </div>
  );
}
