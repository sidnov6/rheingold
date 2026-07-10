/**
 * Zustand store for scenario state (§8.8 sliders + presets) and the current
 * underwrite result. The dossier's Scenario tab writes shocks; every chart on
 * the page reads `result`.
 */

import { create } from "zustand";
import type { Shocks, UnderwriteResult } from "@/lib/types";
import { DEFAULT_SHOCKS } from "@/lib/types";

export interface PresetDef {
  key: string;
  label: string;
  shocks: Partial<Shocks>;
}

/** §8.8 preset chips — must mirror engine scenarios.PRESETS */
export const PRESETS: PresetDef[] = [
  {
    key: "low_wind_2021",
    label: "2021 Low-Wind Year",
    shocks: { production_delta: -0.12, production_years: 3 },
  },
  {
    key: "price_crash_2020",
    label: "2020 Price Crash",
    shocks: { price_level: -0.35, price_years: 2 },
  },
  {
    key: "negative_hour_surge",
    label: "Negative-Hour Surge",
    shocks: { negative_hours_multiplier: 3 },
  },
  {
    key: "rate_shock",
    label: "Rate Shock",
    shocks: { rate_delta_bps: 200, wacc_delta_bps: 100 },
  },
  { key: "capex_overrun", label: "Capex Overrun", shocks: { capex_delta: 0.15 } },
  {
    key: "redispatch_tightening",
    label: "Redispatch Tightening",
    shocks: { curtailment_override: 0.06 },
  },
];

interface ScenarioState {
  shocks: Shocks;
  activePreset: string | null;
  result: UnderwriteResult | null;
  baseResult: UnderwriteResult | null; // unshocked, for deltas
  loading: boolean;
  error: string | null;
  setShock: <K extends keyof Shocks>(key: K, value: Shocks[K]) => void;
  applyPreset: (key: string | null) => void;
  reset: () => void;
  setResult: (r: UnderwriteResult | null) => void;
  setBaseResult: (r: UnderwriteResult | null) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
}

export const useScenario = create<ScenarioState>((set) => ({
  shocks: { ...DEFAULT_SHOCKS },
  activePreset: null,
  result: null,
  baseResult: null,
  loading: false,
  error: null,
  setShock: (key, value) =>
    set((s) => ({ shocks: { ...s.shocks, [key]: value }, activePreset: null })),
  applyPreset: (key) =>
    set(() => {
      if (key === null) return { activePreset: null, shocks: { ...DEFAULT_SHOCKS } };
      const preset = PRESETS.find((p) => p.key === key);
      return {
        activePreset: key,
        shocks: { ...DEFAULT_SHOCKS, ...(preset?.shocks ?? {}) },
      };
    }),
  reset: () => set({ shocks: { ...DEFAULT_SHOCKS }, activePreset: null }),
  setResult: (result) => set({ result }),
  setBaseResult: (baseResult) => set({ baseResult }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
