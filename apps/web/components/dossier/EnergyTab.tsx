"use client";

import type { EnergyResult, FarmDetail } from "@/lib/types";
import { fmtGwh, fmtInt, fmtPct } from "@/lib/format";
import { EnergyDistribution } from "@/components/charts";
import { MetricStat } from "@/components/MetricStat";
import { SourceBadge } from "@/components/SourceBadge";
import { EmptyState } from "@/components/EmptyState";

/**
 * EnergyTab (§11): the uncertainty stack as a dense mono table, the
 * P50/P75/P90 exceedance distribution, and the resource-method disclosure
 * (Path A — renewables.ninja hourly profiles, CC BY-NC · Path B — GWA +
 * windpowerlib power curve).
 */

export interface EnergyTabProps {
  energy: EnergyResult;
  resource: FarmDetail["resource"];
}

export function EnergyTab({ energy, resource }: EnergyTabProps) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-8 rounded border border-line bg-bg1 px-4 py-3">
        <MetricStat label="P50" value={fmtGwh(energy.p50_gwh)} />
        <MetricStat label="P75" value={fmtGwh(energy.p75_gwh)} />
        <MetricStat label="P90 (10y)" value={fmtGwh(energy.p90_gwh)} />
        <MetricStat label="P90 (1y)" value={fmtGwh(energy.p90_1yr_gwh)} />
        <MetricStat label="Net CF" value={fmtPct(energy.net_cf)} />
        <MetricStat label="σ total" value={fmtPct(energy.sigma_total)} hint="combined uncertainty" />
      </div>

      <section className="rounded border border-line bg-bg1 p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base text-hi">Exceedance distribution</h2>
          <span className="text-2xs text-low">illustrative density from P50/P75/P90</span>
        </div>
        <div style={{ height: 280 }}>
          <EnergyDistribution
            p50={energy.p50_gwh}
            p75={energy.p75_gwh}
            p90={energy.p90_gwh}
            p901yr={energy.p90_1yr_gwh}
          />
        </div>
      </section>

      <section className="rounded border border-line bg-bg1 p-4">
        <h2 className="mb-3 text-base text-hi">Uncertainty stack</h2>
        {energy.uncertainty_stack.length === 0 ? (
          <EmptyState title="No uncertainty stack" detail="The engine returned no components." />
        ) : (
          <div className="overflow-x-auto rounded border border-line">
            <table className="w-full border-collapse text-data">
              <thead>
                <tr className="bg-bg2">
                  <th className="h-8 border-b border-line px-3 text-left text-2xs font-medium uppercase tracking-wider text-low">
                    Component
                  </th>
                  <th className="h-8 border-b border-line px-3 text-right text-2xs font-medium uppercase tracking-wider text-low">
                    σ
                  </th>
                  <th className="h-8 border-b border-line px-3 text-center text-2xs font-medium uppercase tracking-wider text-low">
                    In P90
                  </th>
                  <th className="h-8 border-b border-line px-3 text-left text-2xs font-medium uppercase tracking-wider text-low">
                    Note
                  </th>
                </tr>
              </thead>
              <tbody>
                {energy.uncertainty_stack.map((row) => (
                  <tr
                    key={row.component}
                    className="border-b border-line transition-colors last:border-b-0 hover:bg-bg2"
                  >
                    <td className="h-8 whitespace-nowrap px-3 text-hi">{row.component}</td>
                    <td className="num h-8 whitespace-nowrap px-3 text-right text-hi">
                      {fmtPct(row.sigma)}
                    </td>
                    <td className="h-8 px-3 text-center">
                      {row.included_in_p90 ? (
                        <span className="text-pos">✓</span>
                      ) : (
                        <span className="text-low">–</span>
                      )}
                    </td>
                    <td className="h-8 px-3 text-mid">{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded border border-line bg-bg1 p-4">
        <h2 className="mb-2 text-base text-hi">Resource method</h2>
        {resource === null ? (
          <EmptyState
            title="No resource attribution"
            detail="The registry record carries no resource summary for this farm."
          />
        ) : (
          <div className="flex flex-col gap-2 text-data text-mid">
            {resource.method === "ninja" ? (
              <>
                <p>
                  <span className="text-hi">Path A — renewables.ninja.</span> Hourly
                  capacity-factor profile simulated from MERRA-2 reanalysis at the site
                  coordinates, corrected to hub height, then bias-scaled to the engine&apos;s loss
                  stack.
                </p>
                <p className="text-2xs text-low">
                  License note: renewables.ninja data is CC BY-NC 4.0 — non-commercial.
                  RHEINGOLD is a non-commercial portfolio/demo project; commercial use would
                  require replacing this source.
                </p>
              </>
            ) : (
              <p>
                <span className="text-hi">Path B — Global Wind Atlas + windpowerlib.</span> Mean
                wind speed at hub height from GWA, converted through the turbine power curve
                (windpowerlib), Rayleigh-distributed hours, then the engine&apos;s loss stack.
              </p>
            )}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1">
              <MetricStat label="P50 CF (gross)" value={fmtPct(resource.p50_cf)} />
              <MetricStat label="Hub height used" value={`${fmtInt(resource.hub_height_used)} m`} />
              <SourceBadge
                label={resource.method === "ninja" ? "renewables.ninja" : "Global Wind Atlas"}
                license={resource.method === "ninja" ? "CC BY-NC 4.0" : "CC BY 4.0"}
              />
            </div>
            <p className="num text-2xs text-low">{resource.source}</p>
          </div>
        )}
      </section>
    </div>
  );
}

export default EnergyTab;
