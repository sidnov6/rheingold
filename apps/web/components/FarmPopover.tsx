"use client";

import type { FleetFarm } from "@/lib/types";
import { fmtInt, fmtMw, fmtYear } from "@/lib/format";

/**
 * Hover card for a fleet point (§11). Pure positioned presentation —
 * MapCanvas owns the hover state and screen coordinates.
 */

export function FarmPopover({ farm, x, y }: { farm: FleetFarm; x: number; y: number }) {
  return (
    <div
      className="pointer-events-none absolute z-30 w-56 rounded border border-line bg-bg1/95 px-3 py-2 backdrop-blur-sm"
      style={{ left: x + 14, top: y + 14 }}
      role="tooltip"
    >
      <p className="truncate text-data font-medium text-hi">{farm.name}</p>
      <dl className="mt-1.5 flex flex-col gap-0.5 text-2xs">
        <Row label="Capacity">
          <span className="num text-hi">{fmtMw(farm.mw)}</span>
        </Row>
        <Row label="Units">
          <span className="num text-hi">{fmtInt(farm.n)}</span>
        </Row>
        <Row label="Year">
          <span className="num text-hi">{farm.yr !== null ? fmtYear(farm.yr) : "—"}</span>
        </Row>
        <Row label="Manufacturer">
          <span className="truncate text-mid">{farm.man ?? "—"}</span>
        </Row>
        <Row label="Bundesland">
          <span className="truncate text-mid">{farm.bl ?? "—"}</span>
        </Row>
      </dl>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 uppercase tracking-wider text-low">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}
