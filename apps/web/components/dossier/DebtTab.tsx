"use client";

import type { UnderwriteResult } from "@/lib/types";
import { fmtEur, fmtPct, fmtX } from "@/lib/format";
import { MetricStat } from "@/components/MetricStat";
import { DebtScheduleTable } from "@/components/DebtScheduleTable";
import { DSCRChart } from "@/components/charts";

/**
 * DebtTab (§11): DSCR bars vs the 1,20× covenant, coverage & structure stats
 * (LLCR/PLCR/gearing/DSRA), sources & uses, and the dense mono debt schedule.
 * Debt is rhine territory — no gold here except the DSCR data series itself.
 */

export interface DebtTabProps {
  result: UnderwriteResult;
}

function MiniRow({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <tr className={strong ? "border-t border-line" : ""}>
      <td className={`h-8 px-3 text-left ${strong ? "text-hi" : "text-mid"}`}>{label}</td>
      <td className={`num h-8 px-3 text-right ${strong ? "text-hi" : "text-mid"}`}>{value}</td>
    </tr>
  );
}

export function DebtTab({ result }: DebtTabProps) {
  const { debt, valuation, annual } = result;

  // Sources & uses from the engine's own scalars — no invented line items:
  // sources = drawn debt + invested equity; uses = that total less DSRA → capex-side.
  const totalSources = debt.debt_drawn_eur + valuation.equity_invested_eur;
  const capexSide = totalSources - debt.dsra_eur;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-8 rounded border border-line bg-bg1 px-4 py-3">
        <MetricStat label="Min DSCR" value={fmtX(debt.min_dscr)} hint="covenant 1,20×" />
        <MetricStat label="Avg DSCR" value={fmtX(debt.avg_dscr)} />
        <MetricStat label="LLCR" value={fmtX(debt.llcr)} hint="loan-life coverage" />
        <MetricStat label="PLCR" value={fmtX(debt.plcr)} hint="project-life coverage" />
        <MetricStat
          label="Gearing"
          value={fmtPct(debt.gearing)}
          hint={debt.gearing_cap_binding ? "cap binding" : "cap not binding"}
        />
        <MetricStat label="DSRA" value={fmtEur(debt.dsra_eur)} hint="6 months debt service" />
      </div>

      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base text-hi">DSCR by year</h2>
          <span className="text-2xs text-low">covenant line 1,20×</span>
        </div>
        <div style={{ height: 260 }}>
          <DSCRChart annual={annual} covenant={1.2} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="rounded border border-line bg-bg1 p-4 xl:col-span-1">
          <h2 className="mb-3 text-base text-hi">Sources &amp; uses</h2>
          <div className="overflow-hidden rounded border border-line">
            <table className="w-full border-collapse text-data">
              <thead>
                <tr className="bg-bg2">
                  <th className="h-8 border-b border-line px-3 text-left text-2xs font-medium uppercase tracking-wider text-low">
                    Sources
                  </th>
                  <th className="h-8 border-b border-line px-3 text-right text-2xs font-medium uppercase tracking-wider text-low">
                    €
                  </th>
                </tr>
              </thead>
              <tbody>
                <MiniRow label="Senior debt (sculpted)" value={fmtEur(debt.debt_drawn_eur)} />
                <MiniRow label="Sponsor equity" value={fmtEur(valuation.equity_invested_eur)} />
                <MiniRow label="Total" value={fmtEur(totalSources)} strong />
              </tbody>
              <thead>
                <tr className="bg-bg2">
                  <th className="h-8 border-y border-line px-3 text-left text-2xs font-medium uppercase tracking-wider text-low">
                    Uses
                  </th>
                  <th className="h-8 border-y border-line px-3 text-right text-2xs font-medium uppercase tracking-wider text-low">
                    €
                  </th>
                </tr>
              </thead>
              <tbody>
                <MiniRow label="Construction capex" value={fmtEur(capexSide)} />
                <MiniRow label="DSRA funding" value={fmtEur(debt.dsra_eur)} />
                <MiniRow label="Total" value={fmtEur(totalSources)} strong />
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-2xs text-low">
            Debt capacity {fmtEur(debt.debt_capacity_eur)} · drawn {fmtEur(debt.debt_drawn_eur)}
            {debt.gearing_cap_binding ? " — gearing cap binds" : ""}
          </p>
        </section>

        <section className="min-w-0 xl:col-span-2">
          <h2 className="mb-3 text-base text-hi">Debt schedule</h2>
          <DebtScheduleTable annual={annual} />
        </section>
      </div>
    </div>
  );
}

export default DebtTab;
