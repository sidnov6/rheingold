"use client";

import { useMemo, useState } from "react";
import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar, Line } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import type { AnnualSeries } from "@/lib/types";
import { fmtX, fmtYear } from "@/lib/format";
import { EmptyState } from "@/components/EmptyState";
import { C, axisLineProps, numTickProps } from "./theme";
import { ChartTooltip, TipRow, type TipState } from "./ChartTooltip";

/**
 * DSCRChart (§3.4): DSCR bars by year (nulls skipped) + horizontal covenant
 * line (default 1.20×). Bars gold; covenant line turns --neg when breached.
 */

export interface DSCRChartProps {
  annual: AnnualSeries;
  covenant?: number;
}

const MARGIN = { top: 16, right: 12, bottom: 32, left: 48 };

interface Datum {
  year: number;
  dscr: number;
}

function Inner({
  data,
  covenant,
  width,
  height,
}: {
  data: Datum[];
  covenant: number;
  width: number;
  height: number;
}) {
  const [tip, setTip] = useState<TipState | null>(null);
  const xMax = width - MARGIN.left - MARGIN.right;
  const yMax = height - MARGIN.top - MARGIN.bottom;
  const breached = data.some((d) => d.dscr < covenant);

  const xScale = useMemo(
    () =>
      scaleBand<number>({
        domain: data.map((d) => d.year),
        range: [0, xMax],
        padding: 0.35,
      }),
    [data, xMax],
  );
  const yScale = useMemo(() => {
    const hi = Math.max(covenant, ...data.map((d) => d.dscr));
    return scaleLinear<number>({ domain: [0, hi * 1.15], range: [yMax, 0], nice: true });
  }, [data, covenant, yMax]);

  const covenantY = yScale(covenant);
  const lineColor = breached ? C.neg : C.textLow;
  const everyN = Math.max(1, Math.ceil(data.length / Math.floor(xMax / 44)));

  return (
    <>
      <svg width={width} height={height} role="img" aria-label="DSCR by year with covenant line">
        <Group left={MARGIN.left} top={MARGIN.top}>
          {data.map((d) => {
            const x = xScale(d.year) ?? 0;
            const y = yScale(d.dscr);
            const below = d.dscr < covenant;
            return (
              <Bar
                key={d.year}
                x={x}
                y={y}
                width={xScale.bandwidth()}
                height={Math.max(1, yMax - y)}
                fill={C.gold}
                fillOpacity={below ? 0.45 : 0.85}
                stroke={below ? C.neg : "none"}
                strokeWidth={below ? 1 : 0}
                onMouseMove={(e) => {
                  const r = (e.currentTarget as SVGElement).ownerSVGElement?.getBoundingClientRect();
                  if (!r) return;
                  setTip({
                    x: e.clientX - r.left,
                    y: e.clientY - r.top,
                    content: (
                      <>
                        <TipRow label={fmtYear(d.year)} value={fmtX(d.dscr)} accent={C.gold} />
                        {below ? <div className="mt-0.5 text-neg">below covenant</div> : null}
                      </>
                    ),
                  });
                }}
                onMouseLeave={() => setTip(null)}
              />
            );
          })}
          {/* covenant line + subtle label */}
          <Line
            from={{ x: 0, y: covenantY }}
            to={{ x: xMax, y: covenantY }}
            stroke={lineColor}
            strokeWidth={1}
            strokeDasharray="4,3"
          />
          <text
            x={xMax}
            y={covenantY - 5}
            textAnchor="end"
            fontSize={10}
            fontFamily={numTickProps.fontFamily}
            fill={lineColor}
          >
            covenant {fmtX(covenant)}
          </text>
          <AxisLeft
            scale={yScale}
            numTicks={4}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickFormat={(v) => fmtX(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "end" as const, dx: -4, dy: 3 })}
          />
          <AxisBottom
            top={yMax}
            scale={xScale}
            stroke={axisLineProps.stroke}
            tickStroke={axisLineProps.stroke}
            tickValues={data.map((d) => d.year).filter((_, i) => i % everyN === 0)}
            tickFormat={(v) => fmtYear(Number(v))}
            tickLabelProps={() => ({ ...numTickProps, textAnchor: "middle" as const, dy: 4 })}
          />
        </Group>
      </svg>
      <ChartTooltip tip={tip} width={width} />
    </>
  );
}

export function DSCRChart({ annual, covenant = 1.2 }: DSCRChartProps) {
  const data: Datum[] = (annual?.year ?? [])
    .map((year, i) => ({ year, dscr: annual.dscr[i] }))
    .filter((d): d is Datum => d.dscr !== null && d.dscr !== undefined);
  if (data.length === 0) {
    return <EmptyState title="No DSCR series" detail="Debt is fully repaid or no schedule exists." />;
  }
  return (
    <div className="relative h-full min-h-[220px] w-full">
      <ParentSize>
        {({ width, height }) =>
          width > 0 && height > 0 ? (
            <Inner data={data} covenant={covenant} width={width} height={height} />
          ) : null
        }
      </ParentSize>
    </div>
  );
}

export default DSCRChart;
