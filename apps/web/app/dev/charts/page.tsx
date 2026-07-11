"use client";

/**
 * DEV VISUAL TEST HARNESS — /dev/charts
 * Renders every chart/data-display component with SYNTHETIC, clearly-labeled
 * demo props (deterministic, no network). Not linked from navigation.
 */

import type { AnnualSeries, TornadoItem } from "@/lib/types";
import { fmtEurMwh, fmtGwh, fmtPct, fmtX } from "@/lib/format";
import { KPICard } from "@/components/KPICard";
import { MetricStat } from "@/components/MetricStat";
import { VerdictChip } from "@/components/VerdictChip";
import { SourceBadge } from "@/components/SourceBadge";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { DebtScheduleTable } from "@/components/DebtScheduleTable";
import {
  CashflowWaterfall,
  DSCRChart,
  EnergyDistribution,
  NegativeHoursChart,
  PriceChart,
  RevenueStack,
  TornadoChart,
} from "@/components/charts";

// ---------------------------------------------------------------------------
// Deterministic synthetic data (25y project, 42 MW). Pure formulas — no RNG.
// ---------------------------------------------------------------------------

const YEARS = 25;
const START_YEAR = 2026;
const TENOR = 15;
const DEBT0 = 62_000_000;
const RATE = 0.05;

function synthAnnual(): AnnualSeries {
  const year: number[] = [];
  const energy_mwh: number[] = [];
  const revenue_market: number[] = [];
  const revenue_premium: number[] = [];
  const revenue_total: number[] = [];
  const opex_fixed: number[] = [];
  const opex_variable: number[] = [];
  const land_lease: number[] = [];
  const municipal_participation: number[] = [];
  const opex_total: number[] = [];
  const ebitda: number[] = [];
  const depreciation: number[] = [];
  const tax: number[] = [];
  const cfads: number[] = [];
  const debt_balance_bop: number[] = [];
  const interest: number[] = [];
  const principal: number[] = [];
  const debt_service: number[] = [];
  const dscr: (number | null)[] = [];
  const llcr: (number | null)[] = [];
  const equity_cf: number[] = [];

  // annuity payment for the debt leg
  const af = (RATE * Math.pow(1 + RATE, TENOR)) / (Math.pow(1 + RATE, TENOR) - 1);
  const annuity = DEBT0 * af;

  let balance = DEBT0;
  for (let i = 0; i < YEARS; i++) {
    year.push(START_YEAR + i);
    const e = 96_000 * Math.pow(0.994, i) * (1 + 0.04 * Math.sin(i * 1.7)); // MWh, low-wind wobble
    energy_mwh.push(e);
    const price = 52 + 9 * Math.sin(i * 0.55); // €/MWh
    const mkt = e * price;
    const prem = i < 20 ? e * Math.max(0, 61 - price) * 0.85 : 0; // EEG premium leg, 20y
    revenue_market.push(mkt);
    revenue_premium.push(prem);
    revenue_total.push(mkt + prem);
    const fix = 1_890_000 * Math.pow(1.02, i);
    const varOm = e * 4.4;
    const lease = 310_000 * Math.pow(1.02, i);
    const muni = e * 2; // §6 EEG 0,2 ct/kWh
    opex_fixed.push(fix);
    opex_variable.push(varOm);
    land_lease.push(lease);
    municipal_participation.push(muni);
    const ox = fix + varOm + lease + muni;
    opex_total.push(ox);
    const eb = mkt + prem - ox;
    ebitda.push(eb);
    const dep = i < 16 ? DEBT0 / 0.72 / 16 : 0;
    depreciation.push(dep);
    const tx = Math.max(0, (eb - dep - (i < TENOR ? balance * RATE : 0)) * 0.3);
    tax.push(tx);
    const cf = eb - tx;
    cfads.push(cf);
    if (i < TENOR) {
      const int = balance * RATE;
      const prin = annuity - int;
      debt_balance_bop.push(balance);
      interest.push(int);
      principal.push(prin);
      debt_service.push(annuity);
      dscr.push(cf / annuity);
      llcr.push((cf / annuity) * 1.08);
      equity_cf.push(cf - annuity);
      balance -= prin;
    } else {
      debt_balance_bop.push(0);
      interest.push(0);
      principal.push(0);
      debt_service.push(0);
      dscr.push(null);
      llcr.push(null);
      equity_cf.push(cf);
    }
  }
  return {
    year,
    energy_mwh,
    revenue_market,
    revenue_premium,
    revenue_total,
    opex_fixed,
    opex_variable,
    land_lease,
    municipal_participation,
    opex_total,
    ebitda,
    depreciation,
    tax,
    cfads,
    debt_balance_bop,
    interest,
    principal,
    debt_service,
    dscr,
    llcr,
    equity_cf,
  };
}

const ANNUAL = synthAnnual();

const TORNADO: TornadoItem[] = [
  { variable: "price_level", label: "Power price", low_input: "−20 %", high_input: "+20 %", irr_low: 0.041, irr_high: 0.128 },
  { variable: "production", label: "Production (P90↔P10)", low_input: "P90", high_input: "P10", irr_low: 0.052, irr_high: 0.117 },
  { variable: "capex", label: "Capex", low_input: "+15 %", high_input: "−10 %", irr_low: 0.058, irr_high: 0.106 },
  { variable: "rate", label: "Interest rate", low_input: "+200 bp", high_input: "−100 bp", irr_low: 0.066, irr_high: 0.097 },
  { variable: "availability", label: "Availability", low_input: "94 %", high_input: "98 %", irr_low: 0.072, irr_high: 0.093 },
  { variable: "neg_hours", label: "Negative hours", low_input: "×3", high_input: "×1", irr_low: 0.075, irr_high: 0.084 },
];
const BASE_IRR = 0.084;

/** 3 years of daily day-ahead prices + monthly Marktwerte — pure sine synth. */
function synthPrices() {
  const daily: { t: string; v: number }[] = [];
  const marktwerte: { t: string; v: number }[] = [];
  const start = Date.UTC(2023, 0, 1);
  for (let i = 0; i < 365 * 3; i++) {
    const d = new Date(start + i * 86_400_000);
    const seasonal = 22 * Math.sin((i / 365) * 2 * Math.PI + 1.1);
    const weekly = 6 * Math.sin((i / 7) * 2 * Math.PI);
    const noise = 9 * Math.sin(i * 2.3) * Math.sin(i * 0.31);
    daily.push({ t: d.toISOString().slice(0, 10), v: 78 + seasonal + weekly + noise });
  }
  for (let m = 0; m < 36; m++) {
    const d = new Date(Date.UTC(2023, m, 1));
    marktwerte.push({
      t: d.toISOString().slice(0, 10),
      v: 62 + 16 * Math.sin((m / 12) * 2 * Math.PI + 1.3) - m * 0.25,
    });
  }
  return { daily, marktwerte };
}
const PRICES = synthPrices();

const NEG_HOURS = Array.from({ length: 9 }, (_, i) => ({
  year: 2017 + i,
  hours: Math.round(60 + i * i * 8 + 40 * Math.abs(Math.sin(i * 1.9))),
}));

// P50/P75/P90 in GWh
const P50 = 96.4;
const P75 = 89.1;
const P90 = 82.6;
const P90_1YR = 76.9;

// ---------------------------------------------------------------------------

function Panel({ title, note, children, h = 280 }: { title: string; note?: string; children: React.ReactNode; h?: number }) {
  return (
    <section className="rounded border border-line bg-bg1 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base text-hi">{title}</h2>
        {note ? <span className="text-2xs text-low">{note}</span> : null}
      </div>
      <div style={{ height: h }}>{children}</div>
    </section>
  );
}

export default function DevChartsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
      <header className="border-b border-line pb-4">
        <h1 className="text-xl text-hi">DEV — synthetic demo data</h1>
        <p className="mt-1 text-data text-mid">
          Visual test harness for the chart/data-display library. Every number below is a
          deterministic synthetic fixture — nothing here is real market or registry data.
        </p>
      </header>

      <section className="rounded border border-line bg-bg1 p-4">
        <h2 className="mb-3 text-base text-hi">KPICard (count-up on first paint)</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <KPICard label="P50 Energy" value={fmtGwh(P50)} sub="net of losses" countUp />
          <KPICard label="Equity IRR" value={fmtPct(BASE_IRR)} delta="+0,6 pp" deltaSign="pos" countUp />
          <KPICard label="Min DSCR" value={fmtX(1.28)} delta="−0,04×" deltaSign="neg" countUp />
          <KPICard label="Net CF" value={fmtPct(0.262)} sub="capacity factor" countUp />
          <KPICard label="LCOE" value={fmtEurMwh(58.4)} deltaSign="neutral" countUp />
          <KPICard label="Break-even bid" value="6,12 ct/kWh" delta="±0,00" deltaSign="neutral" countUp />
        </div>
      </section>

      <section className="rounded border border-line bg-bg1 p-4">
        <h2 className="mb-3 text-base text-hi">MetricStat · VerdictChip · SourceBadge</h2>
        <div className="flex flex-wrap items-end gap-8">
          <MetricStat label="LLCR" value={fmtX(1.41)} hint="loan-life coverage" />
          <MetricStat label="Gearing" value={fmtPct(0.72)} hint="cap 75 % binding: no" />
          <MetricStat label="Capture rate" value={fmtPct(0.87)} />
          <div className="flex flex-wrap items-center gap-2">
            <VerdictChip verdict="PROCEED" />
            <VerdictChip verdict="PROCEED_WITH_CONDITIONS" />
            <VerdictChip verdict="DECLINE" />
            <VerdictChip verdict={null} />
            <VerdictChip verdict={null} loading />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SourceBadge label="MaStR" url="https://www.marktstammdatenregister.de" license="DL-DE/BY-2-0" />
            <SourceBadge label="SMARD" url="https://www.smard.de" license="CC BY 4.0" />
            <SourceBadge label="Netztransparenz" license="see terms" />
            <SourceBadge label="synthetic fixture" />
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="CashflowWaterfall" note="year 1 of synthetic 25y series">
          <CashflowWaterfall annual={ANNUAL} yearIndex={0} />
        </Panel>
        <Panel title="DSCRChart" note="covenant 1,20× (default)">
          <DSCRChart annual={ANNUAL} />
        </Panel>
        <Panel title="RevenueStack" note="market (rhine) + EEG premium (gold)">
          <RevenueStack annual={ANNUAL} />
        </Panel>
        <Panel title="NegativeHoursChart" note="synthetic §51-hours by year">
          <NegativeHoursChart byYear={NEG_HOURS} />
        </Panel>
      </div>

      <Panel title="TornadoChart" note={`base IRR ${fmtPct(BASE_IRR)}`} h={6 * 34 + 44}>
        <TornadoChart items={TORNADO} baseIrr={BASE_IRR} />
      </Panel>

      <Panel title="EnergyDistribution" note="illustrative density from P50/P75/P90">
        <EnergyDistribution p50={P50} p75={P75} p90={P90} p901yr={P90_1YR} />
      </Panel>

      <Panel title="PriceChart" note="synthetic day-ahead daily Ø + monthly Marktwert" h={320}>
        <PriceChart daily={PRICES.daily} marktwerte={PRICES.marktwerte} />
      </Panel>

      <section className="rounded border border-line bg-bg1 p-4">
        <h2 className="mb-3 text-base text-hi">DebtScheduleTable</h2>
        <DebtScheduleTable annual={ANNUAL} />
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <EmptyState
          title="No memo yet"
          detail="EmptyState demo — synthetic."
          action={<span className="text-2xs text-low">action slot</span>}
        />
        <ErrorState
          title="Underwrite failed"
          detail="ErrorState demo — synthetic."
          hint="POST /api/underwrite → 503"
        />
        <Panel title="PriceChart (empty)" note="EmptyState fallback" h={160}>
          <PriceChart daily={[]} marktwerte={[]} />
        </Panel>
      </div>

      <footer className="border-t border-line pt-3 text-2xs text-low">
        DEV — synthetic demo data · /dev/charts is a visual test harness, not a product page.
      </footer>
    </div>
  );
}
