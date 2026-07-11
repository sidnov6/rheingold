/**
 * Zustand store for the fleet map explorer (§11 "/"). Farms load once from
 * /api/fleet; ALL filtering is client-side via selectFiltered — no API round
 * trip on filter changes.
 */

import { create } from "zustand";
import { API_URL, ApiError, fetchFleet } from "@/lib/api";
import type { FleetFarm, FleetMeta } from "@/lib/types";

/** Normalized key for farms with a null manufacturer / Bundesland. */
export const UNKNOWN_KEY = "(unknown)";

export interface FleetFilters {
  mwRange: [number, number];
  yearRange: [number, number];
  /** Empty array = no manufacturer filter (all pass). Keys via manKey(). */
  manufacturers: string[];
  /** Empty array = no Bundesland filter (all pass). Keys via blKey(). */
  bundeslaender: string[];
}

export interface FleetBounds {
  mw: [number, number];
  year: [number, number];
}

export const manKey = (f: FleetFarm): string => f.man ?? UNKNOWN_KEY;
export const blKey = (f: FleetFarm): string => f.bl ?? UNKNOWN_KEY;

const CURRENT_YEAR = new Date().getFullYear();
const DEFAULT_BOUNDS: FleetBounds = { mw: [0, 100], year: [1990, CURRENT_YEAR] };

/** Data-derived slider bounds (mw floored/ceiled, year min/max). Pure. */
export function selectBounds(farms: FleetFarm[]): FleetBounds {
  if (farms.length === 0) return DEFAULT_BOUNDS;
  let mwLo = Infinity;
  let mwHi = -Infinity;
  let yrLo = Infinity;
  let yrHi = -Infinity;
  for (const f of farms) {
    if (f.mw < mwLo) mwLo = f.mw;
    if (f.mw > mwHi) mwHi = f.mw;
    if (f.yr !== null) {
      if (f.yr < yrLo) yrLo = f.yr;
      if (f.yr > yrHi) yrHi = f.yr;
    }
  }
  if (!Number.isFinite(yrLo)) {
    yrLo = DEFAULT_BOUNDS.year[0];
    yrHi = DEFAULT_BOUNDS.year[1];
  }
  return {
    mw: [Math.floor(mwLo), Math.ceil(mwHi)],
    year: [yrLo, yrHi],
  };
}

/**
 * CLIENT-side filter (§11): pure, allocation-light, safe to call per render
 * behind useMemo. Farms with a null commissioning year always pass the year
 * filter (we cannot judge them); null manufacturer/Bundesland participate as
 * UNKNOWN_KEY in the multi-selects.
 */
export function selectFiltered(farms: FleetFarm[], filters: FleetFilters): FleetFarm[] {
  const [mwLo, mwHi] = filters.mwRange;
  const [yrLo, yrHi] = filters.yearRange;
  const manSet = filters.manufacturers.length > 0 ? new Set(filters.manufacturers) : null;
  const blSet = filters.bundeslaender.length > 0 ? new Set(filters.bundeslaender) : null;
  return farms.filter((f) => {
    if (f.mw < mwLo || f.mw > mwHi) return false;
    if (f.yr !== null && (f.yr < yrLo || f.yr > yrHi)) return false;
    if (manSet !== null && !manSet.has(manKey(f))) return false;
    if (blSet !== null && !blSet.has(blKey(f))) return false;
    return true;
  });
}

/**
 * Fleet meta lives at /api/fleet/meta. lib/api.ts is frozen, so this helper
 * lives here. Gracefully returns null on any failure — meta is decorative
 * (data vintage strip), never load-bearing.
 */
export async function fetchFleetMeta(): Promise<FleetMeta | null> {
  try {
    const res = await fetch(`${API_URL}/api/fleet/meta`);
    if (!res.ok) return null;
    return (await res.json()) as FleetMeta;
  } catch {
    return null;
  }
}

interface FleetState {
  farms: FleetFarm[];
  meta: FleetMeta | null;
  loading: boolean;
  error: string | null;
  filters: FleetFilters;
  hoveredId: string | null;
  selectedId: string | null;
  /** Fetch fleet + meta once; initializes filter ranges to data bounds. */
  load: () => Promise<void>;
  setMwRange: (range: [number, number]) => void;
  setYearRange: (range: [number, number]) => void;
  setManufacturers: (keys: string[]) => void;
  setBundeslaender: (keys: string[]) => void;
  toggleManufacturer: (key: string) => void;
  toggleBundesland: (key: string) => void;
  resetFilters: () => void;
  setHovered: (id: string | null) => void;
  setSelected: (id: string | null) => void;
}

const toggle = (list: string[], key: string): string[] =>
  list.includes(key) ? list.filter((k) => k !== key) : [...list, key];

export const useFleet = create<FleetState>((set, get) => ({
  farms: [],
  meta: null,
  loading: false,
  error: null,
  filters: {
    mwRange: DEFAULT_BOUNDS.mw,
    yearRange: DEFAULT_BOUNDS.year,
    manufacturers: [],
    bundeslaender: [],
  },
  hoveredId: null,
  selectedId: null,

  load: async () => {
    if (get().loading || get().farms.length > 0) return;
    set({ loading: true, error: null });
    try {
      const [farms, meta] = await Promise.all([fetchFleet(), fetchFleetMeta()]);
      const bounds = selectBounds(farms);
      set({
        farms,
        meta,
        loading: false,
        filters: {
          mwRange: bounds.mw,
          yearRange: bounds.year,
          manufacturers: [],
          bundeslaender: [],
        },
      });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `fleet API ${err.status}: ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err);
      set({ loading: false, error: message });
    }
  },

  setMwRange: (mwRange) => set((s) => ({ filters: { ...s.filters, mwRange } })),
  setYearRange: (yearRange) => set((s) => ({ filters: { ...s.filters, yearRange } })),
  setManufacturers: (manufacturers) =>
    set((s) => ({ filters: { ...s.filters, manufacturers } })),
  setBundeslaender: (bundeslaender) =>
    set((s) => ({ filters: { ...s.filters, bundeslaender } })),
  toggleManufacturer: (key) =>
    set((s) => ({
      filters: { ...s.filters, manufacturers: toggle(s.filters.manufacturers, key) },
    })),
  toggleBundesland: (key) =>
    set((s) => ({
      filters: { ...s.filters, bundeslaender: toggle(s.filters.bundeslaender, key) },
    })),
  resetFilters: () =>
    set((s) => {
      const bounds = selectBounds(s.farms);
      return {
        filters: {
          mwRange: bounds.mw,
          yearRange: bounds.year,
          manufacturers: [],
          bundeslaender: [],
        },
      };
    }),
  setHovered: (hoveredId) => set({ hoveredId }),
  setSelected: (selectedId) => set({ selectedId }),
}));
