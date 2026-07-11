"use client";

import * as Slider from "@radix-ui/react-slider";
import clsx from "clsx";
import type { Shocks } from "@/lib/types";
import { fmtInt, fmtPct } from "@/lib/format";
import { useScenario } from "@/stores/scenario";

/**
 * ScenarioSliders (§3.4 / §8.8): 6 radix sliders writing shock values into the
 * scenario store. Ranges are the spec's: price ±40 %, production ±15 %,
 * rate ±300 bp, capex ±25 %, availability 90–99 %, curtailment 0–10 %.
 * Quiet chrome — the rhine range fill marks "how far from base", values in mono.
 */

type NumericKey =
  | "price_level"
  | "production_delta"
  | "rate_delta_bps"
  | "capex_delta"
  | "availability_override"
  | "curtailment_override";

interface SliderDef {
  key: NumericKey;
  label: string;
  min: number;
  max: number;
  step: number;
  /** availability/curtailment are overrides: null = engine default */
  nullable: boolean;
  /** slider position to show while the override is null */
  restingValue: number;
  format: (v: number) => string;
}

const signedPct = (v: number, digits = 0) => `${v > 0 ? "+" : ""}${fmtPct(v, digits)}`;

const SLIDERS: SliderDef[] = [
  {
    key: "price_level",
    label: "Price level",
    min: -0.4,
    max: 0.4,
    step: 0.01,
    nullable: false,
    restingValue: 0,
    format: (v) => signedPct(v),
  },
  {
    key: "production_delta",
    label: "Production",
    min: -0.15,
    max: 0.15,
    step: 0.01,
    nullable: false,
    restingValue: 0,
    format: (v) => signedPct(v),
  },
  {
    key: "rate_delta_bps",
    label: "Interest rate",
    min: -300,
    max: 300,
    step: 25,
    nullable: false,
    restingValue: 0,
    format: (v) => `${v > 0 ? "+" : ""}${fmtInt(v)} bp`,
  },
  {
    key: "capex_delta",
    label: "Capex",
    min: -0.25,
    max: 0.25,
    step: 0.01,
    nullable: false,
    restingValue: 0,
    format: (v) => signedPct(v),
  },
  {
    key: "availability_override",
    label: "Availability",
    min: 0.9,
    max: 0.99,
    step: 0.005,
    nullable: true,
    restingValue: 0.97,
    format: (v) => fmtPct(v, 1),
  },
  {
    key: "curtailment_override",
    label: "Curtailment",
    min: 0,
    max: 0.1,
    step: 0.005,
    nullable: true,
    restingValue: 0,
    format: (v) => fmtPct(v, 1),
  },
];

function ShockSlider({ def }: { def: SliderDef }) {
  const value = useScenario((s) => s.shocks[def.key]) as number | null;
  const setShock = useScenario((s) => s.setShock);
  const isDefault = def.nullable && value === null;
  const position = value ?? def.restingValue;

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label className="text-2xs uppercase tracking-wider text-mid" htmlFor={`slider-${def.key}`}>
          {def.label}
        </label>
        <span className="flex items-baseline gap-2">
          {isDefault ? (
            <span className="text-2xs text-low">engine default</span>
          ) : (
            <span className="num text-data text-hi">{def.format(position)}</span>
          )}
          {def.nullable && !isDefault ? (
            <button
              type="button"
              onClick={() => setShock(def.key, null as Shocks[typeof def.key])}
              className="text-2xs text-low transition-colors hover:text-mid"
            >
              reset
            </button>
          ) : null}
        </span>
      </div>
      <Slider.Root
        id={`slider-${def.key}`}
        className="relative flex h-5 w-full touch-none select-none items-center"
        min={def.min}
        max={def.max}
        step={def.step}
        value={[position]}
        onValueChange={([v]) => setShock(def.key, v as Shocks[typeof def.key])}
        aria-label={def.label}
      >
        <Slider.Track className="relative h-1 grow rounded-full bg-bg2">
          <Slider.Range className="absolute h-full rounded-full bg-rhine-500" />
        </Slider.Track>
        <Slider.Thumb
          className={clsx(
            "block h-3.5 w-3.5 rounded-full border transition-colors",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-dim",
            isDefault
              ? "border-line bg-bg2 hover:bg-bg1"
              : "border-rhine-300 bg-hi hover:bg-rhine-300",
          )}
        />
      </Slider.Root>
      <div className="mt-0.5 flex justify-between text-2xs text-low">
        <span className="num">{def.format(def.min)}</span>
        <span className="num">{def.format(def.max)}</span>
      </div>
    </div>
  );
}

export function ScenarioSliders() {
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
      {SLIDERS.map((def) => (
        <ShockSlider key={def.key} def={def} />
      ))}
    </div>
  );
}

export default ScenarioSliders;
