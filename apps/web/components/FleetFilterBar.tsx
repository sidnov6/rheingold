"use client";

import { useMemo, useState } from "react";
import * as Slider from "@radix-ui/react-slider";
import clsx from "clsx";
import { fmtInt, fmtYear } from "@/lib/format";
import {
  blKey,
  manKey,
  selectBounds,
  selectFiltered,
  useFleet,
  UNKNOWN_KEY,
} from "@/stores/fleet";

/**
 * Top-left floating filter panel (§11): MW range, commissioning-year range,
 * manufacturer multi-select (top-10 by count + "other"), Bundesland
 * multi-select. All filtering is client-side via the fleet store. Quiet
 * chrome — no gold here.
 */

const TOP_N_MANUFACTURERS = 10;

interface Option {
  key: string;
  label: string;
  count: number;
  checked: boolean;
  /** For the synthetic "other" bucket: the real keys it expands to. */
  expandsTo?: string[];
}

export function FleetFilterBar() {
  const farms = useFleet((s) => s.farms);
  const filters = useFleet((s) => s.filters);
  const setMwRange = useFleet((s) => s.setMwRange);
  const setYearRange = useFleet((s) => s.setYearRange);
  const setManufacturers = useFleet((s) => s.setManufacturers);
  const toggleManufacturer = useFleet((s) => s.toggleManufacturer);
  const toggleBundesland = useFleet((s) => s.toggleBundesland);
  const resetFilters = useFleet((s) => s.resetFilters);

  const bounds = useMemo(() => selectBounds(farms), [farms]);
  const filteredCount = useMemo(() => selectFiltered(farms, filters).length, [farms, filters]);

  // Manufacturer options: top 10 by farm count, remainder folded into "other".
  const { manOptions, blOptions } = useMemo(() => {
    const manCounts = new Map<string, number>();
    const blCounts = new Map<string, number>();
    for (const f of farms) {
      const mk = manKey(f);
      const bk = blKey(f);
      manCounts.set(mk, (manCounts.get(mk) ?? 0) + 1);
      blCounts.set(bk, (blCounts.get(bk) ?? 0) + 1);
    }
    const manSorted = Array.from(manCounts.entries()).sort((a, b) => b[1] - a[1]);
    const top = manSorted.slice(0, TOP_N_MANUFACTURERS);
    const rest = manSorted.slice(TOP_N_MANUFACTURERS);
    const selectedMan = new Set(filters.manufacturers);
    const manOpts: Option[] = top.map(([key, count]) => ({
      key,
      label: key,
      count,
      checked: selectedMan.has(key),
    }));
    if (rest.length > 0) {
      const restKeys = rest.map(([key]) => key);
      manOpts.push({
        key: "__other__",
        label: `other (${rest.length})`,
        count: rest.reduce((acc, [, c]) => acc + c, 0),
        checked: restKeys.every((k) => selectedMan.has(k)),
        expandsTo: restKeys,
      });
    }
    const selectedBl = new Set(filters.bundeslaender);
    const blOpts: Option[] = Array.from(blCounts.entries())
      .sort((a, b) => (a[0] === UNKNOWN_KEY ? 1 : b[0] === UNKNOWN_KEY ? -1 : a[0].localeCompare(b[0])))
      .map(([key, count]) => ({ key, label: key, count, checked: selectedBl.has(key) }));
    return { manOptions: manOpts, blOptions: blOpts };
  }, [farms, filters.manufacturers, filters.bundeslaender]);

  const onToggleMan = (opt: Option) => {
    if (opt.expandsTo) {
      const selected = new Set(filters.manufacturers);
      if (opt.checked) {
        setManufacturers(filters.manufacturers.filter((k) => !opt.expandsTo?.includes(k)));
      } else {
        for (const k of opt.expandsTo) selected.add(k);
        setManufacturers(Array.from(selected));
      }
    } else {
      toggleManufacturer(opt.key);
    }
  };

  const mwNarrowed =
    filters.mwRange[0] !== bounds.mw[0] || filters.mwRange[1] !== bounds.mw[1];
  const yearNarrowed =
    filters.yearRange[0] !== bounds.year[0] || filters.yearRange[1] !== bounds.year[1];
  const activeCount =
    (mwNarrowed ? 1 : 0) +
    (yearNarrowed ? 1 : 0) +
    (filters.manufacturers.length > 0 ? 1 : 0) +
    (filters.bundeslaender.length > 0 ? 1 : 0);

  if (farms.length === 0) return null;

  return (
    <div className="absolute left-4 top-4 z-20 flex w-64 flex-col gap-3 rounded border border-line bg-bg1/90 p-3 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <span className="text-2xs font-medium uppercase tracking-wider text-low">Filters</span>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <>
              <span className="num rounded-full bg-bg2 px-1.5 py-0.5 text-2xs text-mid">
                {fmtInt(activeCount)}
              </span>
              <button
                type="button"
                onClick={resetFilters}
                className="text-2xs text-low transition-colors hover:text-mid"
              >
                reset
              </button>
            </>
          )}
        </div>
      </div>

      <RangeSlider
        label="Capacity (MW)"
        min={bounds.mw[0]}
        max={bounds.mw[1]}
        step={1}
        value={filters.mwRange}
        onChange={setMwRange}
        format={fmtInt}
      />
      <RangeSlider
        label="Commissioned"
        min={bounds.year[0]}
        max={bounds.year[1]}
        step={1}
        value={filters.yearRange}
        onChange={setYearRange}
        format={fmtYear}
      />

      <MultiSelect
        label="Manufacturer"
        options={manOptions}
        selectedCount={filters.manufacturers.length}
        onToggle={onToggleMan}
      />
      <MultiSelect
        label="Bundesland"
        options={blOptions}
        selectedCount={filters.bundeslaender.length}
        onToggle={(opt) => toggleBundesland(opt.key)}
      />

      <p className="border-t border-line pt-2 text-2xs text-low">
        <span className="num text-mid">{fmtInt(filteredCount)}</span> farms shown
      </p>
    </div>
  );
}

function RangeSlider({
  label,
  min,
  max,
  step,
  value,
  onChange,
  format,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: [number, number];
  onChange: (v: [number, number]) => void;
  format: (v: number) => string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between">
        <span className="text-2xs uppercase tracking-wider text-low">{label}</span>
        <span className="num text-2xs text-mid">
          {format(value[0])}–{format(value[1])}
        </span>
      </div>
      <Slider.Root
        className="relative flex h-4 w-full touch-none select-none items-center"
        min={min}
        max={max}
        step={step}
        value={value}
        minStepsBetweenThumbs={0}
        onValueChange={(v) => onChange([v[0], v[1]])}
      >
        <Slider.Track className="relative h-px w-full grow bg-line">
          <Slider.Range className="absolute h-px bg-mid" />
        </Slider.Track>
        <Slider.Thumb
          className="block h-3 w-3 rounded-full border border-line bg-hi transition-transform hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-dim"
          aria-label={`${label} minimum`}
        />
        <Slider.Thumb
          className="block h-3 w-3 rounded-full border border-line bg-hi transition-transform hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-dim"
          aria-label={`${label} maximum`}
        />
      </Slider.Root>
    </div>
  );
}

function MultiSelect({
  label,
  options,
  selectedCount,
  onToggle,
}: {
  label: string;
  options: Option[];
  selectedCount: number;
  onToggle: (opt: Option) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative flex flex-col gap-1">
      <span className="text-2xs uppercase tracking-wider text-low">{label}</span>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={clsx(
          "flex items-center justify-between rounded border border-line bg-bg2 px-2 py-1.5 text-2xs transition-colors",
          selectedCount > 0 ? "text-hi" : "text-mid",
          "hover:border-mid/40",
        )}
      >
        <span>
          {selectedCount > 0 ? (
            <>
              <span className="num">{fmtInt(selectedCount)}</span> selected
            </>
          ) : (
            "all"
          )}
        </span>
        <span aria-hidden className="text-low">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-30"
            aria-hidden
            onClick={() => setOpen(false)}
          />
          <ul className="absolute left-0 top-full z-40 mt-1 max-h-56 w-full overflow-y-auto rounded border border-line bg-bg1 py-1">
            {options.map((opt) => (
              <li key={opt.key}>
                <label className="flex cursor-pointer items-center gap-2 px-2 py-1 text-2xs text-mid transition-colors hover:bg-bg2 hover:text-hi">
                  <input
                    type="checkbox"
                    checked={opt.checked}
                    onChange={() => onToggle(opt)}
                    className="h-3 w-3 accent-current"
                  />
                  <span className="min-w-0 flex-1 truncate">{opt.label}</span>
                  <span className="num shrink-0 text-low">{fmtInt(opt.count)}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
