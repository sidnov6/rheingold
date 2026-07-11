"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";

/**
 * KPICard (§3.4): label / mono value / delta. 600ms count-up on first paint
 * only (§3.3), respecting prefers-reduced-motion. Value arrives pre-formatted
 * (de-DE via lib/format.ts); the count-up re-animates the numeric portion.
 */

export interface KPICardProps {
  label: string;
  value: string;
  delta?: string;
  deltaSign?: "pos" | "neg" | "neutral";
  sub?: string;
  countUp?: boolean;
}

/** Parse the first de-DE formatted number out of a display string. */
function parseDeNumber(
  value: string,
): { num: number; decimals: number; match: string } | null {
  const m = value.match(/-?\d[\d.,]*/);
  if (!m) return null;
  const raw = m[0];
  const num = Number(raw.replace(/\./g, "").replace(",", "."));
  if (!Number.isFinite(num)) return null;
  const commaIdx = raw.lastIndexOf(",");
  const decimals = commaIdx === -1 ? 0 : raw.length - commaIdx - 1;
  return { num, decimals, match: raw };
}

const DELTA_COLOR: Record<NonNullable<KPICardProps["deltaSign"]>, string> = {
  pos: "text-pos",
  neg: "text-neg",
  neutral: "text-mid",
};

export function KPICard({ label, value, delta, deltaSign = "neutral", sub, countUp }: KPICardProps) {
  const [display, setDisplay] = useState(countUp ? "" : value);
  const hasAnimated = useRef(false);

  useEffect(() => {
    // Animate only on first mount, only when asked to.
    if (!countUp || hasAnimated.current) {
      setDisplay(value);
      return;
    }
    hasAnimated.current = true;
    const parsed = parseDeNumber(value);
    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!parsed || reduceMotion) {
      setDisplay(value);
      return;
    }
    const fmt = new Intl.NumberFormat("de-DE", {
      minimumFractionDigits: parsed.decimals,
      maximumFractionDigits: parsed.decimals,
    });
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / 600, 1);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out
      if (t < 1) {
        setDisplay(value.replace(parsed.match, fmt.format(parsed.num * eased)));
        raf = requestAnimationFrame(tick);
      } else {
        setDisplay(value);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, countUp]);

  return (
    <div className="rounded border border-line bg-bg1 px-4 py-3">
      <div className="text-2xs uppercase tracking-wider text-low">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="num text-lg text-hi">{display || " "}</span>
        {delta ? (
          <span className={clsx("num text-2xs", DELTA_COLOR[deltaSign])}>{delta}</span>
        ) : null}
      </div>
      {sub ? <div className="mt-0.5 text-2xs text-low">{sub}</div> : null}
    </div>
  );
}

export default KPICard;
