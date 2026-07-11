"use client";

import * as HoverCard from "@radix-ui/react-hover-card";
import type { EvidenceItem } from "@/lib/types";
import { fmt2, fmtCtKwh, fmtEur, fmtEurMwh, fmtGwh, fmtInt, fmtMw, fmtPct, fmtX } from "@/lib/format";

/**
 * Gold wax-seal citation chip (§3, §9.7). Hover → dark evidence card.
 * An unknown id renders as a broken seal in --neg: orphan citations must be
 * visible, never hidden — honesty is the feature.
 */

function formatEvidenceValue(value: number | string, unit: string): string {
  if (typeof value === "string") return unit ? `${value} ${unit}` : value;
  switch (unit) {
    case "ct/kWh":
      return fmtCtKwh(value);
    case "€/MWh":
    case "EUR/MWh":
      return fmtEurMwh(value);
    case "€":
    case "EUR":
      return fmtEur(value);
    case "GWh":
      return fmtGwh(value);
    case "MW":
      return fmtMw(value);
    case "%":
      return fmtPct(value);
    case "×":
    case "x":
      return fmtX(value);
    default: {
      const s = Number.isInteger(value) ? fmtInt(value) : fmt2(value);
      return unit ? `${s} ${unit}` : s;
    }
  }
}

export function CitationSeal({
  evidence,
  id,
}: {
  evidence: EvidenceItem | undefined;
  id: string;
}) {
  const broken = evidence === undefined;
  return (
    <HoverCard.Root openDelay={150} closeDelay={100}>
      <HoverCard.Trigger asChild>
        <button
          type="button"
          className={
            broken
              ? "num mx-0.5 inline-flex translate-y-[-1px] items-center gap-1 rounded-full border border-dashed border-neg px-1.5 py-px align-middle text-2xs leading-none text-neg"
              : "num mx-0.5 inline-flex translate-y-[-1px] items-center gap-1 rounded-full bg-gold-dim px-1.5 py-px align-middle text-2xs leading-none text-gold-500 transition-colors hover:text-gold-400"
          }
          aria-label={broken ? `Orphan citation ${id}` : `Evidence ${id}`}
        >
          <span aria-hidden>{broken ? "◌" : "◉"}</span>
          {id}
        </button>
      </HoverCard.Trigger>
      <HoverCard.Portal>
        <HoverCard.Content
          side="top"
          sideOffset={6}
          collisionPadding={12}
          className="z-50 w-72 rounded border border-line bg-bg2 p-3 text-2xs text-mid"
        >
          {broken ? (
            <div>
              <div className="num text-neg">{id}</div>
              <p className="mt-1 text-mid">
                Orphan citation — no evidence with this id exists in the store. The
                validator flags this; it is shown rather than hidden.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="num text-gold-500">{evidence.id}</span>
                <span className="uppercase tracking-wider text-low">{evidence.type}</span>
              </div>
              <div className="text-base text-hi">{evidence.label}</div>
              <div className="num text-md text-gold-500">
                {formatEvidenceValue(evidence.value, evidence.unit)}
              </div>
              {evidence.formula_ref && (
                <div>
                  <span className="text-low">formula&nbsp;</span>
                  <span className="num text-mid">{evidence.formula_ref}</span>
                </div>
              )}
              {evidence.inputs.length > 0 && (
                <div className="flex flex-wrap items-baseline gap-1">
                  <span className="text-low">inputs</span>
                  {evidence.inputs.map((inp) => (
                    <span key={inp} className="num rounded bg-bg1 px-1 text-mid">
                      {inp}
                    </span>
                  ))}
                </div>
              )}
              {evidence.url && (
                <a
                  href={evidence.url}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-rhine-300 underline decoration-line underline-offset-2 hover:text-hi"
                >
                  {evidence.url}
                </a>
              )}
              {evidence.retrieved_at && (
                <div>
                  <span className="text-low">retrieved&nbsp;</span>
                  <span className="num text-mid">{evidence.retrieved_at}</span>
                </div>
              )}
            </div>
          )}
          <HoverCard.Arrow className="fill-[var(--bg-2)]" />
        </HoverCard.Content>
      </HoverCard.Portal>
    </HoverCard.Root>
  );
}
