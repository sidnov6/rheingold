"use client";

import clsx from "clsx";
import type { UnderwriteResult } from "@/lib/types";
import { fmt1, fmt2, fmtCtKwh, fmtDelta, fmtEurMwh, fmtGwh, fmtPct, fmtX } from "@/lib/format";
import { KPICard, type KPICardProps } from "@/components/KPICard";
import { CashflowWaterfall } from "@/components/charts";

/**
 * OverviewTab (§11): 6 KPICards — P50 GWh · net CF · equity IRR · min DSCR ·
 * LCOE · break-even bid — each with a delta vs the unshocked base result,
 * above the year-1 CashflowWaterfall. In-flight underwrites shimmer the grid.
 */

export interface OverviewTabProps {
  result: UnderwriteResult;
  base: UnderwriteResult | null;
  loading: boolean;
}

const EPS = 1e-9;

/** signed de-DE delta string; fmt handles the minus for negatives */
const signed = (v: number, fmt: (n: number) => string) => (v > 0 ? `+${fmt(v)}` : fmt(v));

function delta(
  cur: number | null,
  base: number | null | undefined,
  fmt: (v: number) => string,
  higherIsBetter: boolean,
): Pick<KPICardProps, "delta" | "deltaSign"> {
  if (cur === null || base === null || base === undefined) return {};
  const d = cur - base;
  if (Math.abs(d) < EPS) return {};
  return {
    delta: signed(d, fmt),
    deltaSign: d > 0 === higherIsBetter ? "pos" : "neg",
  };
}

export function OverviewTab({ result, base, loading }: OverviewTabProps) {
  const shocked = base !== null && result !== base;
  const b = shocked ? base : null;
  const { energy, debt, valuation, annual } = result;

  const kpis: KPICardProps[] = [
    {
      label: "P50 Energy",
      value: fmtGwh(energy.p50_gwh),
      sub: "net, first year",
      ...delta(energy.p50_gwh, b?.energy.p50_gwh, (v) => `${fmt1(v)} GWh`, true),
    },
    {
      label: "Net CF",
      value: fmtPct(energy.net_cf),
      sub: "capacity factor",
      ...delta(energy.net_cf, b?.energy.net_cf, (v) => fmtDelta(v).replace("+", ""), true),
    },
    {
      label: "Equity IRR",
      value: valuation.equity_irr === null ? "–" : fmtPct(valuation.equity_irr),
      sub: valuation.equity_irr === null ? "no sign change in equity CF" : undefined,
      ...delta(
        valuation.equity_irr,
        b?.valuation.equity_irr ?? null,
        (v) => fmtDelta(v).replace("+", ""),
        true,
      ),
    },
    {
      label: "Min DSCR",
      value: fmtX(debt.min_dscr),
      sub: "covenant 1,20×",
      ...delta(debt.min_dscr, b?.debt.min_dscr, (v) => `${fmt2(v)}×`, true),
    },
    {
      label: "LCOE",
      value: fmtEurMwh(valuation.lcoe_eur_mwh),
      ...delta(valuation.lcoe_eur_mwh, b?.valuation.lcoe_eur_mwh, (v) => `${fmt2(v)} €/MWh`, false),
    },
    {
      label: "Break-even bid",
      value:
        valuation.breakeven_bid_ct_kwh === null ? "–" : fmtCtKwh(valuation.breakeven_bid_ct_kwh),
      sub: "at target equity IRR",
      ...delta(
        valuation.breakeven_bid_ct_kwh,
        b?.valuation.breakeven_bid_ct_kwh ?? null,
        (v) => `${fmt2(v)} ct/kWh`,
        false,
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div
        aria-busy={loading}
        className={clsx(
          "grid grid-cols-2 gap-3 transition-opacity xl:grid-cols-3",
          loading && "animate-pulse opacity-60",
        )}
      >
        {kpis.map((k) => (
          <KPICard key={k.label} {...k} countUp />
        ))}
      </div>

      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base text-hi">Cash flow — first operating year</h2>
          <span className="text-2xs text-low">
            Revenue → opex → EBITDA → tax → debt service → equity CF
          </span>
        </div>
        <div style={{ height: 300 }}>
          <CashflowWaterfall annual={annual} yearIndex={0} />
        </div>
      </section>
    </div>
  );
}

export default OverviewTab;
