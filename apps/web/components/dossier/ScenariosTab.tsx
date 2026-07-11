"use client";

import clsx from "clsx";
import { PRESETS, useScenario } from "@/stores/scenario";
import { ScenarioSliders } from "./ScenarioSliders";

/**
 * ScenariosTab (§11): §8.8 preset chips above the six shock sliders, plus
 * reset. Every chart on the dossier reads the store's `result`, so moving
 * anything here re-prices the whole page (250ms debounce upstream).
 */

export interface ScenariosTabProps {
  /** true when this farm ships precomputed preset results (showcase mode) */
  hasShowcasePresets: boolean;
  /** true when a custom-slider underwrite failed because the API is asleep */
  engineWaking: boolean;
}

export function ScenariosTab({ hasShowcasePresets, engineWaking }: ScenariosTabProps) {
  const activePreset = useScenario((s) => s.activePreset);
  const applyPreset = useScenario((s) => s.applyPreset);
  const reset = useScenario((s) => s.reset);
  const loading = useScenario((s) => s.loading);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base text-hi">Stress presets</h2>
          {hasShowcasePresets ? (
            <span className="text-2xs text-low">precomputed — instant, works offline</span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((p) => {
            const active = activePreset === p.key;
            return (
              <button
                key={p.key}
                type="button"
                aria-pressed={active}
                onClick={() => applyPreset(active ? null : p.key)}
                className={clsx(
                  "h-7 rounded-full border px-3 text-2xs transition-colors",
                  active
                    ? "border-rhine-300 bg-bg2 text-hi"
                    : "border-line bg-bg1 text-mid hover:border-rhine-500 hover:text-hi",
                )}
              >
                {p.label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-base text-hi">Shock sliders</h2>
          <div className="flex items-center gap-3">
            {loading ? (
              <span className="animate-pulse text-2xs text-low" aria-live="polite">
                re-pricing…
              </span>
            ) : null}
            <button
              type="button"
              onClick={reset}
              className="h-7 rounded-sm border border-line bg-bg2 px-3 text-2xs font-medium uppercase tracking-wider text-mid transition-colors hover:text-hi"
            >
              Reset
            </button>
          </div>
        </div>
        <ScenarioSliders />
        {engineWaking ? (
          <p className="mt-4 border-t border-line pt-3 text-2xs text-warn" role="status">
            live engine waking… custom shocks need the API — showing the last computed result.
            Preset chips stay instant{hasShowcasePresets ? " (precomputed)" : ""}.
          </p>
        ) : (
          <p className="mt-4 border-t border-line pt-3 text-2xs text-low">
            Shocks re-price through the deterministic engine (/api/underwrite) — nothing on this
            page is interpolated client-side.
          </p>
        )}
      </section>
    </div>
  );
}

export default ScenariosTab;
