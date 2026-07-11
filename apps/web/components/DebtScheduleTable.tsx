"use client";

import type { AnnualSeries } from "@/lib/types";
import { fmtEur, fmtX, fmtYear } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";

/**
 * DebtScheduleTable (§3.2/§3.4): dense mono table — 13px, 32px rows,
 * right-aligned numerals, bg2 header, hairline borders. Terminal density.
 */

export interface DebtScheduleTableProps {
  annual: AnnualSeries;
}

const COLS = [
  { key: "year", label: "Year", align: "left" as const },
  { key: "bop", label: "BoP Balance", align: "right" as const },
  { key: "interest", label: "Interest", align: "right" as const },
  { key: "principal", label: "Principal", align: "right" as const },
  { key: "ds", label: "Debt Service", align: "right" as const },
  { key: "cfads", label: "CFADS", align: "right" as const },
  { key: "dscr", label: "DSCR", align: "right" as const },
];

export function DebtScheduleTable({ annual }: DebtScheduleTableProps) {
  if (!annual || annual.year.length === 0) {
    return <EmptyState title="No debt schedule" detail="Run an underwrite to build the sculpted schedule." />;
  }
  return (
    <div className="overflow-x-auto rounded border border-line">
      <table className="w-full border-collapse text-data">
        <thead>
          <tr className="bg-bg2">
            {COLS.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={`h-8 whitespace-nowrap border-b border-line px-3 text-2xs font-medium uppercase tracking-wider text-low ${
                  c.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {annual.year.map((yr, i) => (
            <tr key={yr} className="border-b border-line transition-colors last:border-b-0 hover:bg-bg2">
              <td className="num h-8 whitespace-nowrap px-3 text-left text-mid">{fmtYear(yr)}</td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-hi">
                {fmtEur(annual.debt_balance_bop[i] ?? 0)}
              </td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-mid">
                {fmtEur(annual.interest[i] ?? 0)}
              </td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-mid">
                {fmtEur(annual.principal[i] ?? 0)}
              </td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-hi">
                {fmtEur(annual.debt_service[i] ?? 0)}
              </td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-hi">
                {fmtEur(annual.cfads[i] ?? 0)}
              </td>
              <td className="num h-8 whitespace-nowrap px-3 text-right text-hi">
                {annual.dscr[i] === null || annual.dscr[i] === undefined ? (
                  <span className="text-low">–</span>
                ) : (
                  fmtX(annual.dscr[i] as number)
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DebtScheduleTable;
