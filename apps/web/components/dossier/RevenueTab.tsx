"use client";

import { useEffect, useState } from "react";
import type { UnderwriteResult } from "@/lib/types";
import { API_URL } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { MetricStat } from "@/components/MetricStat";
import { SourceBadge } from "@/components/SourceBadge";
import { EmptyState } from "@/components/EmptyState";
import { NegativeHoursChart, PriceChart, RevenueStack } from "@/components/charts";

/**
 * RevenueTab (§11): SMARD day-ahead prices + monthly Marktwert overlay,
 * revenue stack by year (market + EEG premium), capture-rate stat, and
 * §51 negative-hours-by-year bars. Market series come from
 * GET /api/market?farm_id= — absent/asleep API degrades to EmptyStates
 * (the underwrite-driven charts stay live).
 */

export interface RevenueTabProps {
  farmId: string;
  result: UnderwriteResult;
}

interface MarketSeries {
  daily: { t: string; v: number }[];
  marktwerte: { t: string; v: number }[];
  negative_hours_by_year: { year: number; hours: number }[];
}

type MarketState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; data: MarketSeries };

/** tolerant parse — any missing series becomes an empty array, never fabricated */
function parseMarket(raw: unknown): MarketSeries {
  const o = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  return {
    daily: arr(o.daily),
    marktwerte: arr(o.marktwerte),
    negative_hours_by_year: arr(o.negative_hours_by_year),
  };
}

/** local helper (§10 has no market route yet — degrade gracefully) */
async function fetchMarket(farmId: string): Promise<MarketSeries> {
  const res = await fetch(`${API_URL}/api/market?farm_id=${encodeURIComponent(farmId)}`);
  if (!res.ok) throw new Error(`market fetch failed (${res.status})`);
  return parseMarket(await res.json());
}

const marketCache = new Map<string, MarketSeries>();

export function RevenueTab({ farmId, result }: RevenueTabProps) {
  const [market, setMarket] = useState<MarketState>(() => {
    const cached = marketCache.get(farmId);
    return cached ? { status: "ready", data: cached } : { status: "loading" };
  });

  useEffect(() => {
    if (marketCache.has(farmId)) return;
    let cancelled = false;
    fetchMarket(farmId)
      .then((data) => {
        marketCache.set(farmId, data);
        if (!cancelled) setMarket({ status: "ready", data });
      })
      .catch(() => {
        if (!cancelled) setMarket({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [farmId]);

  const marketDown =
    market.status === "error" ||
    (market.status === "ready" && market.data.daily.length === 0 && market.data.marktwerte.length === 0);

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base text-hi">Day-ahead price · monthly Marktwert</h2>
          <div className="flex gap-1.5">
            <SourceBadge label="SMARD" url="https://www.smard.de" license="CC BY 4.0" />
            <SourceBadge label="Netztransparenz" license="attribution" />
          </div>
        </div>
        <div style={{ height: 320 }}>
          {market.status === "loading" ? (
            <div className="h-full w-full animate-pulse rounded bg-bg2" aria-busy="true" />
          ) : marketDown ? (
            <EmptyState
              title="Market data unavailable"
              detail="The live market API did not answer — no price series to show. Nothing is synthesized in its place."
            />
          ) : (
            <PriceChart daily={market.data.daily} marktwerte={market.data.marktwerte} />
          )}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded border border-line bg-bg1 p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-base text-hi">Revenue stack by year</h2>
            <span className="text-2xs text-low">market + EEG premium</span>
          </div>
          <div style={{ height: 260 }}>
            <RevenueStack annual={result.annual} />
          </div>
        </section>

        <section className="rounded border border-line bg-bg1 p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-base text-hi">Negative price hours</h2>
            <span className="text-2xs text-low">§51 EEG — premium suspended</span>
          </div>
          <div style={{ height: 260 }}>
            {market.status === "loading" ? (
              <div className="h-full w-full animate-pulse rounded bg-bg2" aria-busy="true" />
            ) : market.status === "error" || market.data.negative_hours_by_year.length === 0 ? (
              <EmptyState
                title="No negative-hours series"
                detail="Requires the live market API (SMARD hourly prices)."
              />
            ) : (
              <NegativeHoursChart byYear={market.data.negative_hours_by_year} />
            )}
          </div>
        </section>
      </div>

      <div className="flex flex-wrap gap-8 rounded border border-line bg-bg1 px-4 py-3">
        <MetricStat
          label="Capture rate"
          value={fmtPct(result.valuation.capture_rate)}
          hint="wind-weighted vs baseload price"
        />
      </div>
    </div>
  );
}

export default RevenueTab;
