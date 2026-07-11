"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";
import { FleetFilterBar } from "@/components/FleetFilterBar";
import { FleetStats } from "@/components/FleetStats";
import { MapCanvas } from "@/components/MapCanvas";
import { useFleet } from "@/stores/fleet";

/**
 * "/" — full-bleed map explorer (§11). The hero IS the fleet: dark Germany
 * basemap, ~30k gold turbine points shimmering in. Fleet loads once into the
 * zustand store on mount; filter/hover/click all live client-side.
 *
 * Failure honesty: if the fleet API is down or the data mart isn't built,
 * the basemap stays visible with an error banner — never a crash.
 */

export default function MapExplorerPage() {
  const load = useFleet((s) => s.load);
  const loading = useFleet((s) => s.loading);
  const error = useFleet((s) => s.error);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Basemap + deck.gl points (fills the container) */}
      <MapCanvas />

      {/* The one allowed gradient: barely-visible radial gold glow (§3.3) */}
      <div aria-hidden className="map-glow pointer-events-none absolute inset-0 z-10" />

      {/* Skeleton pulse while the fleet loads (§11) */}
      {loading && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-10 animate-pulse bg-bg1/30"
        />
      )}

      <FleetFilterBar />
      <FleetStats />

      {error && (
        <div className="absolute left-1/2 top-4 z-30 w-full max-w-md -translate-x-1/2 px-4">
          <ErrorState
            title="fleet data not built yet"
            detail="Run make data to build the fleet mart, then reload."
            hint={error}
            className="bg-bg1/95 backdrop-blur-sm"
          />
        </div>
      )}
    </div>
  );
}
