"use client";

import { useMemo } from "react";
import { fmtInt } from "@/lib/format";
import { selectFiltered, useFleet } from "@/stores/fleet";

/**
 * Top-right fleet stats strip (§11): total MW, unit count, farm count, data
 * vintage. Numbers reflect the ACTIVE filters so the strip re-prices live as
 * the analyst narrows the fleet. Skeleton pulse while loading.
 */

export function FleetStats() {
  const farms = useFleet((s) => s.farms);
  const filters = useFleet((s) => s.filters);
  const meta = useFleet((s) => s.meta);
  const loading = useFleet((s) => s.loading);

  const stats = useMemo(() => {
    const filtered = selectFiltered(farms, filters);
    let mw = 0;
    let units = 0;
    for (const f of filtered) {
      mw += f.mw;
      units += f.n;
    }
    return { mw, units, farmCount: filtered.length };
  }, [farms, filters]);

  return (
    <div className="absolute right-4 top-4 z-20 flex divide-x divide-line rounded border border-line bg-bg1/90 backdrop-blur-sm">
      <Stat label="Total MW" value={loading ? null : fmtInt(Math.round(stats.mw))} />
      <Stat label="Units" value={loading ? null : fmtInt(stats.units)} />
      <Stat label="Farms" value={loading ? null : fmtInt(stats.farmCount)} />
      <Stat
        label="MaStR vintage"
        value={loading ? null : (meta?.mastr_snapshot_date ?? "—")}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex min-w-[84px] flex-col gap-0.5 px-3 py-2">
      <span className="whitespace-nowrap text-2xs uppercase tracking-wider text-low">
        {label}
      </span>
      {value === null ? (
        <span className="h-[18px] w-14 animate-pulse rounded-sm bg-bg2" aria-hidden />
      ) : (
        <span className="num whitespace-nowrap text-data text-hi">{value}</span>
      )}
    </div>
  );
}
