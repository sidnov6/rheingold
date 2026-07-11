"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  LineType,
  LineStyle,
  CrosshairMode,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { fmt2 } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";

/**
 * PriceChart (§3.4/§11 Revenue): lightweight-charts — SMARD day-ahead daily
 * series (rhine area) + monthly Marktwert step overlay (gold). Two series max.
 * Theme colors resolved from the §3.1 CSS variables at mount.
 */

export interface PriceChartProps {
  daily: { t: string; v: number }[];
  marktwerte: { t: string; v: number }[];
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Resolved #rrggbb token → rgba() at given alpha (canvas cannot use var()). */
function withAlpha(resolvedHex: string, alpha: number): string {
  const m = resolvedHex.match(/^#([0-9a-f]{6})$/i);
  if (!m) return resolvedHex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** sort ascending + dedupe by day — lightweight-charts requires strict order */
function toSeries(points: { t: string; v: number }[]): { time: Time; value: number }[] {
  const byDay = new Map<string, number>();
  for (const p of points) {
    const day = p.t.slice(0, 10);
    if (day.length === 10 && Number.isFinite(p.v)) byDay.set(day, p.v);
  }
  return Array.from(byDay.entries())
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([time, value]) => ({ time: time as Time, value }));
}

export function PriceChart({ daily, marktwerte }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const hasData = daily.length > 0 || marktwerte.length > 0;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !hasData) return;

    const gold = cssVar("--gold-500");
    const rhine = cssVar("--rhine-500");
    const border = cssVar("--border");
    const textLow = cssVar("--text-low");
    const textMid = cssVar("--text-mid");
    const bg2 = cssVar("--bg-2");

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: textLow,
        fontSize: 10,
        fontFamily: "IBM Plex Mono, ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: border, style: LineStyle.Dotted },
        horzLines: { color: border, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: border },
      timeScale: { borderColor: border, timeVisible: false },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: textMid, width: 1, style: LineStyle.Dashed, labelBackgroundColor: bg2 },
        horzLine: { color: textMid, width: 1, style: LineStyle.Dashed, labelBackgroundColor: bg2 },
      },
      localization: {
        locale: "de-DE",
        priceFormatter: (p: number) => fmt2(p),
      },
      handleScroll: { mouseWheel: false, pressedMouseMove: true },
      handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true },
    });
    chartRef.current = chart;

    const dailyData = toSeries(daily);
    if (dailyData.length > 0) {
      const area = chart.addAreaSeries({
        lineColor: rhine,
        topColor: withAlpha(rhine, 0.25),
        bottomColor: withAlpha(rhine, 0.02),
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "Day-ahead",
      });
      area.setData(dailyData);
    }

    const mwData = toSeries(marktwerte);
    if (mwData.length > 0) {
      const line = chart.addLineSeries({
        color: gold,
        lineWidth: 2,
        lineType: LineType.WithSteps,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "Marktwert Wind an Land",
      });
      line.setData(mwData);
    }

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
    // series data identity: re-create the chart when inputs change
  }, [daily, marktwerte, hasData]);

  if (!hasData) {
    return (
      <EmptyState
        title="No price data"
        detail="SMARD day-ahead and Netztransparenz Marktwert series unavailable."
      />
    );
  }
  return (
    <div className="relative h-full min-h-[240px] w-full">
      <div ref={containerRef} className="absolute inset-0" />
      <div className="pointer-events-none absolute left-1 top-1 z-10 flex gap-3 text-[10px]">
        {daily.length > 0 ? (
          <span className="flex items-center gap-1 text-low">
            <span aria-hidden className="inline-block h-0.5 w-3 bg-rhine-500" /> Day-ahead (daily Ø)
          </span>
        ) : null}
        {marktwerte.length > 0 ? (
          <span className="flex items-center gap-1 text-low">
            <span aria-hidden className="inline-block h-0.5 w-3 bg-gold-500" /> Marktwert (monthly)
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default PriceChart;
