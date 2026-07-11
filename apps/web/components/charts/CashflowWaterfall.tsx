"use client";

import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar, Line } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import type { AnnualSeries } from "@/lib/types";
import { fmtEur } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, catTickProps, numTickProps } from "./theme";
import { ChartTooltip, TipRow, type TipState } from "./ChartTooltip";

/**
 * CashflowWaterfall (§11 Overview): one operating year —
 * Revenue → −opex lines → EBITDA → −tax → −debt service → Equity CF.
 * Gold for inflows/results, rhine for debt service, --neg for costs.
 */

export interface CashflowWaterfallProps {
  annual: AnnualSeries;
  yearIndex?: number;
}

type Kind = "inflow" | "cost" | "debt" | "total";

interface Step {
  key: string;
  label: string;
  short: string;
  kind: Kind;
  /** signed flow for floating steps; absolute level for totals */
  value: number;
  y0: number;
  y1: number;
}

const KIND_FILL: Record<Kind, string> = {
  inflow: C.gold,
  total: C.gold,
  cost: C.neg,
  debt: C.rhine,
};

const MARGIN = { top: 12, right: 12, bottom: 42, left: 56 };

function buildSteps(a: AnnualSeries, i: number): Step[] {
  const defs: { key: string; label: string; short: string; kind: Kind; delta?: number; total?: number }[] = [
    { key: "rev", label: "Revenue", short: "Rev", kind: "inflow", delta: a.revenue_total[i] },
    { key: "fix", label: "Fixed O&M", short: "Fix", kind: "cost", delta: -a.opex_fixed[i] },
    { key: "var", label: "Variable O&M", short: "Var", kind: "cost", delta: -a.opex_variable[i] },
    { key: "lease", label: "Land lease", short: "Lease", kind: "cost", delta: -a.land_lease[i] },
    { key: "muni", label: "Municipal participation (§6 EEG)", short: "Muni", kind: "cost", delta: -a.municipal_participation[i] },
    { key: "ebitda", label: "EBITDA", short: "EBITDA", kind: "total", total: a.ebitda[i] },
    { key: "tax", label: "Tax", short: "Tax", kind: "cost", delta: -a.tax[i] },
    { key: "ds", label: "Debt service", short: "DS", kind: "debt", delta: -a.debt_service[i] },
    { key: "ecf", label: "Equity cash flow", short: "Eq CF", kind: "total", total: a.equity_cf[i] },
  ];
  const steps: Step[] = [];
  let running = 0;
  for (const d of defs) {
    if (d.total !== undefined) {
      steps.push({ ...d, kind: d.kind, value: d.total, y0: 0, y1: d.total });
      running = d.total;
    } else {
      const delta = d.delta ?? 0;
      steps.push({ ...d, kind: d.kind, value: delta, y0: running, y1: running + delta });
      running += delta;
    }
  }
  return steps;
}

function Inner({ steps, width, height }: { steps: Step[]; width: number; height: number }) {
  const [tip, setTip] = useState<TipState | null>(null);
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;

  const xScale = useMemo(
    () =>
      scaleBand<string>({
        domain: steps.map((s) => s.key),
        range: [0, xMax],
        padding: 0.3,
      }),
    [steps, xMax],
  );
  const yScale = useMemo(() => {
    const lo = Math.min(0, ...steps.flatMap((s) => [s.y0, s.y1]));
    const hi = Math.max(0, ...steps.flatMap((s) => [s.y0, s.y1]));
    return scaleLinear<number>({ domain: [lo, hi * 1.06], range: [yMax, 0], nice: true });
  }, [steps, yMax]);

  return (
    <>
      <svg width={width} height={height} role="img" aria-label="Cash flow waterfall">
        <Group left={MARGIN.left} top={MARGIN.top}>
          {/* zero line */}
          <Line
            from={{ x: 0, y: yScale(0) }}
            to={{ x: xMax, y: yScale(0) }}
            stroke={C.border}
            strokeWidth={1}
          />
          {steps.map((s, idx) => {
            const x = xScale(s.key) ?? 0;
            const bw = xScale.bandwidth();
            const top = yScale(Math.max(s.y0, s.y1));
            const h = Math.max(1, Math.abs(yScale(s.y0) - yScale(s.y1)));
            const next = steps[idx + 1];
            return (
              <Group key={s.key}>
                <Bar
                  x={x}
                  y={top}
                  width={bw}
                  height={h}
                  fill={KIND_FILL[s.kind]}
                  fillOpacity={s.kind === "total" ? 0.9 : 0.75}
                  onMouseMove={(e) => {
                    const r = (e.currentTarget as SVGElement).ownerSVGElement?.getBoundingClientRect();
                    if (!r) return;
                    setTip({
                      x: e.clientX - r.left,
                      y: e.clientY - r.top,
                      content: <TipRow label={s.label} value={fmtEur(s.value)} accent={KIND_FILL[s.kind]} />,
                    });
                  }}
                  onMouseLeave={() => setTip(null)}
                />
                {/* connector to the next bar */}
                {next ? (
                  <Line
                    from={{ x: x + bw, y: yScale(s.y1) }}
                    to={{ x: (xScale(next.key) ?? 0), y: yScale(next.kind === "total" ? next.y1 : next.y0) }}
                    stroke={C.textLow}
                    strokeWidth={1}
                    strokeDasharray="2,3"
                    strokeOpacity={0.6}
                  />
                ) : null}
              </Group>
            );
          })}
          <AxisLeft
            scale={yScale}
            numTicks={5}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtEur(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "end" as const, dx: -4, dy: 3 })}
          />
          <AxisBottom
            top={yMax}
            scale={xScale}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(k) => steps.find((s) => s.key === k)?.short ?? String(k)}
            tickLabelProps={() => ({ ...catTickProps, textAnchor: "middle" as const, dy: 4 })}
          />
        </Group>
      </svg>
      <ChartTooltip tip={tip} width={width} />
    </>
  );
}

export function CashflowWaterfall({ annual, yearIndex = 0 }: CashflowWaterfallProps) {
  const i = yearIndex;
  if (!annual || annual.year.length === 0 || i < 0 || i >= annual.year.length) {
    return <EmptyState title="No cash flows" detail="Run an underwrite to build the waterfall." />;
  }
  const steps = buildSteps(annual, i);
  return (
    <div className="relative h-full min-h-[240px] w-full">
      <ParentSize>
        {({ width, height }) =>
          width > 0 && height > 0 ? <Inner steps={steps} width={width} height={height} /> : null
        }
      </ParentSize>
    </div>
  );
}

export default CashflowWaterfall;
