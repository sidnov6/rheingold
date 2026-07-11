"use client";

import clsx from "clsx";
import type { Verdict } from "@/lib/types";

/**
 * VerdictChip (§3.4): the underwriting verdict as a quiet stamp-colored chip.
 * PROCEED → --stamp-proceed · PROCEED_WITH_CONDITIONS → --stamp-conditions ·
 * DECLINE → --stamp-decline · null → NOT UNDERWRITTEN in text-low.
 */

export interface VerdictChipProps {
  verdict: Verdict | null;
  loading?: boolean;
}

const VERDICT_STYLE: Record<Verdict, { text: string; className: string }> = {
  PROCEED: { text: "PROCEED", className: "border-stamp-proceed text-stamp-proceed" },
  PROCEED_WITH_CONDITIONS: {
    text: "PROCEED WITH CONDITIONS",
    className: "border-stamp-conditions text-stamp-conditions",
  },
  DECLINE: { text: "DECLINE", className: "border-stamp-decline text-stamp-decline" },
};

export function VerdictChip({ verdict, loading }: VerdictChipProps) {
  if (loading) {
    return (
      <span
        className="inline-flex animate-pulse items-center rounded border border-line bg-bg2 px-2.5 py-1 text-2xs uppercase tracking-widest text-low"
        aria-live="polite"
      >
        Underwriting…
      </span>
    );
  }
  if (verdict === null) {
    return (
      <span className="inline-flex items-center rounded border border-line px-2.5 py-1 text-2xs uppercase tracking-widest text-low">
        Not underwritten
      </span>
    );
  }
  const s = VERDICT_STYLE[verdict];
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded border px-2.5 py-1 text-2xs font-semibold uppercase tracking-widest",
        s.className,
      )}
    >
      {s.text}
    </span>
  );
}

export default VerdictChip;
