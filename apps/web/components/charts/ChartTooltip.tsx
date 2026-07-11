"use client";

/**
 * Minimal chart tooltip: absolutely positioned inside the chart's relative
 * wrapper. bg2 surface, hairline border, mono numbers (§3).
 */

export interface TipState {
  x: number;
  y: number;
  content: React.ReactNode;
}

export function ChartTooltip({ tip, width }: { tip: TipState | null; width: number }) {
  if (!tip) return null;
  // keep the tooltip inside the chart on the right edge
  const flip = tip.x > width - 140;
  return (
    <div
      className="pointer-events-none absolute z-10 rounded border border-line bg-bg2 px-2 py-1.5 text-2xs leading-4 text-mid"
      style={{
        left: flip ? undefined : tip.x + 12,
        right: flip ? width - tip.x + 12 : undefined,
        top: Math.max(0, tip.y - 8),
      }}
    >
      {tip.content}
    </div>
  );
}

/** label:value row for tooltip bodies — value in mono. */
export function TipRow({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 whitespace-nowrap">
      <span className="flex items-center gap-1.5">
        {accent ? (
          <span aria-hidden className="inline-block h-2 w-2 rounded-sm" style={{ background: accent }} />
        ) : null}
        <span className="text-low">{label}</span>
      </span>
      <span className="num text-hi">{value}</span>
    </div>
  );
}
